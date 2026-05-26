"""
app/services/dingtalk_api.py — 钉钉群机器人 / 应用消息 推送

提供两种推送能力:
1. send_bot_message(): 群机器人 Webhook 推送(免开发,最快接入)
   - 支持 text / markdown / actionCard 三种 msgtype
   - 自动加签(timestamp + secret)
2. send_app_message(): 企业应用消息(精准到个人,需 AppKey/AppSecret/AgentId)
   - 走 OAPI access_token 通道

群机器人配置:
- 钉钉群 > 群设置 > 智能群助手 > 添加机器人 > 自定义
- 安全设置选「加签」模式,把 Secret 写到 DINGTALK_BOT_SECRET
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Optional

import httpx

from app.config import settings

# ────────────────────────────────────────────────────────────────
# 群机器人 Webhook 推送(推荐)
# ────────────────────────────────────────────────────────────────


def _sign_webhook(secret: str) -> tuple[str, str]:
    """钉钉加签算法: HMAC-SHA256(secret, "{timestamp}\n{secret}") -> base64 -> urlencode"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


def _build_webhook_url() -> Optional[str]:
    """组装带加签参数的 webhook 完整 URL,未配置时返回 None"""
    if not settings.dingtalk_bot_webhook:
        return None
    url = settings.dingtalk_bot_webhook
    if settings.dingtalk_bot_secret:
        ts, sign = _sign_webhook(settings.dingtalk_bot_secret)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={ts}&sign={sign}"
    return url


async def send_bot_text(
    content: str,
    at_mobiles: Optional[list[str]] = None,
    at_all: bool = False,
) -> dict:
    """
    群机器人 text 消息。
    @某人需用手机号,@所有人 at_all=True。

    返回钉钉响应 JSON,errcode=0 表示成功。
    """
    url = _build_webhook_url()
    if not url:
        return {"errcode": -1, "errmsg": "dingtalk webhook not configured"}

    payload = {
        "msgtype": "text",
        "text": {"content": content},
        "at": {
            "atMobiles": at_mobiles or [],
            "isAtAll": at_all,
        },
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        return resp.json()


async def send_bot_markdown(
    title: str,
    text: str,
    at_mobiles: Optional[list[str]] = None,
    at_all: bool = False,
) -> dict:
    """
    群机器人 markdown 消息(钉钉支持的语法子集:标题/列表/图片/链接/引用)。
    """
    url = _build_webhook_url()
    if not url:
        return {"errcode": -1, "errmsg": "dingtalk webhook not configured"}

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
        "at": {
            "atMobiles": at_mobiles or [],
            "isAtAll": at_all,
        },
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        return resp.json()


async def send_bot_action_card(
    title: str,
    text: str,
    single_title: str,
    single_url: str,
) -> dict:
    """
    群机器人 actionCard 消息(整体跳转卡片,适合战情日报/周报链接)。
    """
    url = _build_webhook_url()
    if not url:
        return {"errcode": -1, "errmsg": "dingtalk webhook not configured"}

    payload = {
        "msgtype": "actionCard",
        "actionCard": {
            "title": title,
            "text": text,
            "singleTitle": single_title,
            "singleURL": single_url,
            "btnOrientation": "0",
        },
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)
        return resp.json()


# ────────────────────────────────────────────────────────────────
# 企业应用消息(精准到个人,可选)
# ────────────────────────────────────────────────────────────────

DINGTALK_OAPI_BASE = "https://oapi.dingtalk.com"

_token_cache: dict[str, object] = {"token": None, "expires_at": 0.0}


async def _get_app_access_token() -> Optional[str]:
    """获取钉钉企业应用 access_token,带内存缓存。未配置时返回 None。"""
    if not (settings.dingtalk_app_key and settings.dingtalk_app_secret):
        return None

    now = time.time()
    cached = _token_cache.get("token")
    # _token_cache: dict[str, object];运行时 expires_at 字段语义 float
    expires_at = float(_token_cache.get("expires_at", 0))  # type: ignore[arg-type]
    if cached and expires_at > now + 60:
        return str(cached)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{DINGTALK_OAPI_BASE}/gettoken",
            params={
                "appkey": settings.dingtalk_app_key,
                "appsecret": settings.dingtalk_app_secret,
            },
        )
        data = resp.json()

    token = data.get("access_token")
    if not token:
        return None

    _token_cache["token"] = token
    _token_cache["expires_at"] = now + data.get("expires_in", 7200)
    return token


async def send_app_text(userid: str, content: str) -> dict:
    """
    向单个钉钉员工推送工作通知(text)。
    userid: 钉钉企业内的员工 userid。
    """
    token = await _get_app_access_token()
    if not token or not settings.dingtalk_agent_id:
        return {"errcode": -1, "errmsg": "dingtalk app not configured"}

    payload = {
        "agent_id": int(settings.dingtalk_agent_id),
        "userid_list": userid,
        "msg": {
            "msgtype": "text",
            "text": {"content": content},
        },
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{DINGTALK_OAPI_BASE}/topapi/message/corpconversation/asyncsend_v2",
            params={"access_token": token},
            json=payload,
        )
        return resp.json()


def is_bot_configured() -> bool:
    return bool(settings.dingtalk_bot_webhook)


def is_app_configured() -> bool:
    return bool(settings.dingtalk_app_key and settings.dingtalk_app_secret and settings.dingtalk_agent_id)
