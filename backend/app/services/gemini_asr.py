"""
app/services/gemini_asr.py — 用 Gemini 多模态做语音转写(可选 provider)

Gemini 原生支持音频输入(audio_url / inline base64 audio),
通过 LiteLLM 网关 /chat/completions 接口提交即可。

适用场景:
- ASR_PROVIDER=gemini 时启用
- 单段音频 ≤ 5 分钟(讯飞流式更适合长音频)

格式支持:wav/mp3/aac/flac/m4a/ogg(Gemini Pro/Flash 都支持)
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger("aipm.asr.gemini")


def is_configured() -> bool:
    """ASR_PROVIDER=gemini 且 LiteLLM 网关已配置"""
    if (settings.asr_provider or "").lower() != "gemini":
        return False
    return bool(settings.new_api_base_url and settings.new_api_key)


def _guess_audio_mime(file_name: str, fallback: str) -> str:
    name = (file_name or "").lower()
    if name.endswith(".wav"):
        return "audio/wav"
    if name.endswith(".mp3"):
        return "audio/mpeg"
    if name.endswith(".m4a"):
        return "audio/mp4"
    if name.endswith(".aac"):
        return "audio/aac"
    if name.endswith(".ogg"):
        return "audio/ogg"
    if name.endswith(".flac"):
        return "audio/flac"
    if name.endswith(".webm"):
        return "audio/webm"
    return fallback or "audio/wav"


async def transcribe(
    audio_bytes: bytes,
    *,
    file_name: str = "voice.wav",
    mime_type: str = "audio/wav",
    timeout: float = 60.0,
) -> Optional[str]:
    """
    用 Gemini 多模态做语音转写。返回纯文本;失败返回 None。
    """
    if not is_configured():
        logger.info("Gemini ASR not configured, skip")
        return None

    if not audio_bytes:
        return None

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    audio_mime = _guess_audio_mime(file_name, mime_type)

    # LiteLLM/OpenAI 兼容协议下,Gemini 音频通过 input_audio 类型传入
    payload = {
        "model": "gemini-2.5-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "请把这段音频完整准确地转写成中文文本,"
                            "只输出转写结果本身,不要添加前缀、解释或标点修饰。"
                        ),
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": audio_mime.split("/")[-1],
                        },
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 2048,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.new_api_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.new_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        text = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        if not text:
            logger.warning("gemini ASR returned empty content: %s", data)
            return None
        return text.strip()
    except Exception:
        logger.exception("gemini ASR failed")
        return None
