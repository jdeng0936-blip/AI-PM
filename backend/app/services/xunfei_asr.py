"""
app/services/xunfei_asr.py — 讯飞流式语音识别(IAT)WebSocket 客户端

讯飞 IAT (Interactive Audio Text) 协议:
- WebSocket 接入: wss://iat-api.xfyun.cn/v2/iat
- 鉴权: HMAC-SHA256(api_key + date + request_line) + base64 -> authorization URL 参数
- 音频分帧:每帧 ≤ 1280 字节(40ms 16k pcm),status=0/1/2 表示首/中/末帧
- 返回:多段 JSON,通过 ws+wp+cw 拼接最终文本

参考: https://www.xfyun.cn/doc/asr/voicedictation/API.html

降级:
- ASR_PROVIDER=none 或缺凭证 → transcribe() 返回 None,不报错
- 非 wav/pcm/16k 输入暂不做格式转换(后续可接 ffmpeg),返回错误提示
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime
from email.utils import formatdate
from typing import Optional
from urllib.parse import urlencode

import websockets

from app.config import settings

logger = logging.getLogger("aipm.asr")

IAT_HOST = "iat-api.xfyun.cn"
IAT_PATH = "/v2/iat"
IAT_URL = f"wss://{IAT_HOST}{IAT_PATH}"


def is_configured() -> bool:
    """只有 ASR_PROVIDER=xunfei 且凭证齐全才视为已配置"""
    if (settings.asr_provider or "").lower() != "xunfei":
        return False
    return bool(
        settings.xunfei_app_id
        and settings.xunfei_api_key
        and settings.xunfei_api_secret
        and not settings.xunfei_app_id.startswith("your_")
    )


def _build_auth_url() -> str:
    """生成带鉴权参数的 WebSocket URL"""
    now = datetime.utcnow()
    date_str = formatdate(timeval=now.timestamp(), usegmt=True)

    signature_origin = f"host: {IAT_HOST}\ndate: {date_str}\nGET {IAT_PATH} HTTP/1.1"
    signature_sha = hmac.new(
        settings.xunfei_api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature_b64 = base64.b64encode(signature_sha).decode("utf-8")

    authorization_origin = (
        f'api_key="{settings.xunfei_api_key}", '
        'algorithm="hmac-sha256", '
        'headers="host date request-line", '
        f'signature="{signature_b64}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

    params = {
        "authorization": authorization,
        "date": date_str,
        "host": IAT_HOST,
    }
    return f"{IAT_URL}?{urlencode(params)}"


def _build_first_frame(audio_chunk: bytes, *, audio_format: str = "raw") -> dict:
    return {
        "common": {"app_id": settings.xunfei_app_id},
        "business": {
            "language": "zh_cn",
            "domain": "iat",
            "accent": "mandarin",
            "vad_eos": 5000,
            "ptt": 0,  # 不加标点(0)/加标点(1)
            "dwa": "wpgs",  # 动态修正
        },
        "data": {
            "status": 0,
            "format": "audio/L16;rate=16000" if audio_format == "raw" else audio_format,
            "encoding": "raw",
            "audio": base64.b64encode(audio_chunk).decode("utf-8"),
        },
    }


def _build_mid_frame(audio_chunk: bytes) -> dict:
    return {
        "data": {
            "status": 1,
            "format": "audio/L16;rate=16000",
            "encoding": "raw",
            "audio": base64.b64encode(audio_chunk).decode("utf-8"),
        }
    }


def _build_last_frame() -> dict:
    return {
        "data": {
            "status": 2,
            "format": "audio/L16;rate=16000",
            "encoding": "raw",
            "audio": "",
        }
    }


def _decode_result(message: str) -> str:
    """解析讯飞返回的 JSON,拼接成纯文本"""
    payload = json.loads(message)
    if payload.get("code") != 0:
        logger.warning("xunfei iat error: %s", payload)
        return ""
    data = payload.get("data", {})
    result = data.get("result", {})
    ws_list = result.get("ws", [])
    text_parts = []
    for w in ws_list:
        for cw in w.get("cw", []):
            text_parts.append(cw.get("w", ""))
    return "".join(text_parts)


async def transcribe(audio_pcm16k: bytes, timeout: float = 30.0) -> Optional[str]:
    """
    主入口:把一段 16kHz PCM(16bit, mono)音频转写成中文文本。

    输入: 完整的 raw PCM 字节流(.wav 也支持,讯飞会忽略 header)
    输出: 转写文本;失败/未配置时返回 None
    """
    if not is_configured():
        logger.info("ASR not configured, skip transcription")
        return None

    if not audio_pcm16k:
        return None

    try:
        url = _build_auth_url()
        async with websockets.connect(url, ping_timeout=timeout, close_timeout=5) as ws:
            # ── 分帧发送 ──
            chunk_size = 1280  # 40ms * 16k * 16bit / 8
            total_len = len(audio_pcm16k)
            offset = 0
            is_first = True

            while offset < total_len:
                chunk = audio_pcm16k[offset : offset + chunk_size]
                if is_first:
                    frame = _build_first_frame(chunk)
                    is_first = False
                else:
                    frame = _build_mid_frame(chunk)
                await ws.send(json.dumps(frame))
                offset += chunk_size
                # 节流:讯飞要求每帧间隔约 40ms
                await asyncio.sleep(0.04)

            # ── 末帧 ──
            await ws.send(json.dumps(_build_last_frame()))

            # ── 接收结果(直到 status==2 或连接关闭) ──
            transcript_parts: list[str] = []
            last_segment = ""  # 用于 wpgs 动态修正去重
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning("xunfei iat recv timeout")
                    break

                payload = json.loads(msg)
                if payload.get("code") != 0:
                    logger.warning("xunfei iat error code: %s", payload)
                    break

                data = payload.get("data", {})
                # ws.recv() 返回 str|bytes;_decode_result 只接受 str(JSON 字符串)
                segment = _decode_result(msg if isinstance(msg, str) else msg.decode("utf-8"))

                # wpgs 模式下 pgs=apd 是追加,pgs=rpl 是替换
                pgs = data.get("result", {}).get("pgs")
                if pgs == "rpl":
                    # 替换前面的部分段(简化处理:直接保留最后一段,忽略 rg 区间)
                    last_segment = segment
                else:
                    if last_segment:
                        transcript_parts.append(last_segment)
                        last_segment = ""
                    last_segment = segment

                if data.get("status") == 2:
                    if last_segment:
                        transcript_parts.append(last_segment)
                    break

            return "".join(transcript_parts).strip() or None

    except Exception:
        logger.exception("xunfei transcribe failed")
        return None
