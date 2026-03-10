from __future__ import annotations
"""
app/services/wechat_api.py — 企业微信 API 工具函数

功能：
1. 消息签名校验（防伪造回调）
2. AES-256-CBC 消息解密（企微加密模式）
3. 向员工/管理层推送文本消息 / 卡片消息
4. 获取并缓存 access_token
"""
import hashlib
import base64
import struct
import time
from typing import Optional

import httpx
from Crypto.Cipher import AES

from app.config import settings

# ── access_token 内存缓存（避免频繁请求）──────────────────────────
_token_cache: dict[str, object] = {"token": None, "expires_at": 0}

WECHAT_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


def verify_signature(msg_signature: str, timestamp: str, nonce: str, encrypt: str = "") -> bool:
    """
    校验企微消息签名（防止伪造回调）。
    sha1(sorted([token, timestamp, nonce, encrypt])) == msg_signature
    """
    items = sorted([settings.wechat_token, timestamp, nonce, encrypt])
    sha1 = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
    return sha1 == msg_signature


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


async def fetch_media_url(media_id: str) -> Optional[str]:
    """
    将企微临时素材 media_id 转换为可访问的 URL。
    生产环境应将文件转存至 OSS，此处返回下载流 URL 作为简化实现。
    """
    token = await _get_access_token()
    # 实际生产：需下载后上传 OSS，并返回 OSS 公网 URL
    return f"{WECHAT_API_BASE}/media/get?access_token={token}&media_id={media_id}"
