from __future__ import annotations

"""
app/services/wechat_api.py — 企业微信 API 工具函数

功能：
1. 消息签名校验（防伪造回调）
2. AES-256-CBC 消息解密（企微加密模式）
3. 向员工/管理层推送文本消息 / 卡片消息
4. 获取并缓存 access_token
"""
import base64
import hashlib
import hmac
import struct
import time

# ── access_token 内存缓存（避免频繁请求）──────────────────────────
# dict[str, Any] 而非 dict[str, object] — 缓存字段语义上是 (token: str|None, expires_at: float)
# 用 Any 让取值不需要每次 cast,生产语义清晰
from typing import (
    Any,  # noqa: E402
    Optional,
)

import httpx
from Crypto.Cipher import AES

from app.config import settings

_token_cache: dict[str, Any] = {"token": None, "expires_at": 0}

WECHAT_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


def verify_signature(msg_signature: str, timestamp: str, nonce: str, encrypt: str = "") -> bool:
    """
    校验企微消息签名（防止伪造回调）。
    sha1(sorted([token, timestamp, nonce, encrypt])) == msg_signature
    """
    try:
        if abs(time.time() - int(timestamp)) > 600:
            return False
    except (TypeError, ValueError):
        return False
    items = sorted([settings.wechat_token, timestamp, nonce, encrypt])
    sha1 = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
    return hmac.compare_digest(sha1, msg_signature)


def decrypt_message(encrypted_msg: str) -> str:
    """
    AES-256-CBC 解密企微消息体。
    返回解密后的 XML 明文字符串。
    """
    aes_key = base64.b64decode(settings.wechat_encoding_aes_key + "=")
    cipher = AES.new(aes_key, AES.MODE_CBC, aes_key[:16])
    decrypted = cipher.decrypt(base64.b64decode(encrypted_msg))

    # 去除 PKCS7 填充
    pad = decrypted[-1]
    content = decrypted[20:-pad]  # 前20字节为随机串

    # 读取消息长度（大端序 4 字节）
    msg_len = struct.unpack(">I", content[:4])[0]
    return content[4 : 4 + msg_len].decode("utf-8")


async def _get_access_token() -> str:
    """获取企微 access_token，带内存缓存（有效期7200秒）"""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{WECHAT_API_BASE}/gettoken",
            params={
                "corpid": settings.wechat_corp_id,
                "corpsecret": settings.wechat_corp_secret,
            },
        )
        data = resp.json()

    token = data["access_token"]
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + data.get("expires_in", 7200)
    return token


async def send_text_message(to_user: str, content: str) -> None:
    """
    向指定员工推送企微文本消息。
    to_user: 企微 userid（即 FromUserName）
    """
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{WECHAT_API_BASE}/message/send",
            params={"access_token": token},
            json={
                "touser": to_user,
                "msgtype": "text",
                "agentid": settings.wechat_agent_id,
                "text": {"content": content},
                "safe": 0,
            },
        )


async def send_markdown_message(to_user: str, content: str) -> None:
    """
    向指定员工推送 Markdown 格式消息（支持标题/粗体/链接）。
    注意：markdown msgtype 不支持在企微手机端完全渲染，建议用于 PC 端管理层。
    """
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{WECHAT_API_BASE}/message/send",
            params={"access_token": token},
            json={
                "touser": to_user,
                "msgtype": "markdown",
                "agentid": settings.wechat_agent_id,
                "markdown": {"content": content},
            },
        )


async def fetch_media_url(media_id: str, owner_id: str = "wechat") -> Optional[str]:
    """
    下载企微临时素材并转存到 OSS/本地降级存储，避免把应用级 access_token 入库或发给 LLM。
    """
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{WECHAT_API_BASE}/media/get",
            params={"access_token": token, "media_id": media_id},
        )
        resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip()
    if content_type == "application/json":
        return None

    from app.services import oss_service

    ext_by_type = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    file_name = f"{media_id}{ext_by_type.get(content_type, '.bin')}"
    storage_key = oss_service.make_storage_key(kind="image", user_id=owner_id, file_name=file_name)
    return await oss_service.upload_bytes(storage_key, resp.content, content_type)


# ────────────────────────────────────────────────────────────────
# 企微群机器人 Webhook 推送(免开发,适合战情日报/风险预警群推)
# ────────────────────────────────────────────────────────────────


async def send_bot_text(content: str, mentioned_list: Optional[list[str]] = None) -> dict:
    """
    企微群机器人 text 消息。
    mentioned_list: ['@all'] 或 userid 列表(企微 userid,需机器人在群里)。
    """
    if not settings.wechat_bot_webhook:
        return {"errcode": -1, "errmsg": "wechat bot webhook not configured"}

    payload = {
        "msgtype": "text",
        "text": {
            "content": content,
            "mentioned_list": mentioned_list or [],
        },
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(settings.wechat_bot_webhook, json=payload)
        return resp.json()


async def send_bot_markdown(content: str) -> dict:
    """
    企微群机器人 markdown 消息。
    支持的语法见: https://developer.work.weixin.qq.com/document/path/91770
    """
    if not settings.wechat_bot_webhook:
        return {"errcode": -1, "errmsg": "wechat bot webhook not configured"}

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(settings.wechat_bot_webhook, json=payload)
        return resp.json()


def is_app_configured() -> bool:
    return bool(settings.wechat_corp_id and settings.wechat_corp_secret and settings.wechat_agent_id)


def is_bot_configured() -> bool:
    return bool(settings.wechat_bot_webhook)
