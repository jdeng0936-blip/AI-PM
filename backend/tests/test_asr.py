"""
tests/test_asr.py — ASR provider 路由 + 配置感知测试

不调用真实讯飞/Gemini,仅验证:
- is_configured 在缺/有凭证时正确开关
- _resolve_provider 按 ASR_PROVIDER 偏好 + 可用性回退
- transcribe 在未配置时优雅返回 None
"""

from __future__ import annotations

import pytest

from app.services import gemini_asr, xunfei_asr

# ────────────────────────────────────────────────────────────────
# is_configured 的关闭语义
# ────────────────────────────────────────────────────────────────


def test_xunfei_not_configured_when_provider_is_not_xunfei(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "asr_provider", "gemini")
    monkeypatch.setattr(settings, "xunfei_app_id", "real-id")
    monkeypatch.setattr(settings, "xunfei_api_key", "k")
    monkeypatch.setattr(settings, "xunfei_api_secret", "s")
    assert xunfei_asr.is_configured() is False


def test_xunfei_not_configured_with_placeholder_id(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "asr_provider", "xunfei")
    monkeypatch.setattr(settings, "xunfei_app_id", "your_app_id")
    monkeypatch.setattr(settings, "xunfei_api_key", "k")
    monkeypatch.setattr(settings, "xunfei_api_secret", "s")
    assert xunfei_asr.is_configured() is False


def test_gemini_not_configured_when_provider_is_not_gemini(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "asr_provider", "xunfei")
    monkeypatch.setattr(settings, "new_api_base_url", "http://x")
    monkeypatch.setattr(settings, "new_api_key", "k")
    assert gemini_asr.is_configured() is False


def test_gemini_configured_when_provider_is_gemini(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "asr_provider", "gemini")
    monkeypatch.setattr(settings, "new_api_base_url", "http://x")
    monkeypatch.setattr(settings, "new_api_key", "k")
    assert gemini_asr.is_configured() is True


# ────────────────────────────────────────────────────────────────
# 转写在未配置时返回 None,不报错
# ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_xunfei_transcribe_returns_none_if_unconfigured(monkeypatch):
    monkeypatch.setattr(xunfei_asr, "is_configured", lambda: False)
    res = await xunfei_asr.transcribe(b"\x00" * 100)
    assert res is None


@pytest.mark.asyncio
async def test_gemini_transcribe_returns_none_if_unconfigured(monkeypatch):
    monkeypatch.setattr(gemini_asr, "is_configured", lambda: False)
    res = await gemini_asr.transcribe(b"\x00" * 100, file_name="a.wav")
    assert res is None


@pytest.mark.asyncio
async def test_gemini_transcribe_returns_none_on_empty():
    res = await gemini_asr.transcribe(b"", file_name="a.wav")
    assert res is None


def test_gemini_mime_guess():
    from app.services.gemini_asr import _guess_audio_mime

    assert _guess_audio_mime("a.wav", "audio/x") == "audio/wav"
    assert _guess_audio_mime("a.mp3", "audio/x") == "audio/mpeg"
    assert _guess_audio_mime("a.m4a", "audio/x") == "audio/mp4"
    assert _guess_audio_mime("unknown.xyz", "audio/aac") == "audio/aac"


# ────────────────────────────────────────────────────────────────
# router 的 provider 解析
# ────────────────────────────────────────────────────────────────


def test_resolve_provider_prefers_configured(monkeypatch):
    from app.config import settings
    from app.routers.asr import _resolve_provider

    # 明确选 gemini 且可用
    monkeypatch.setattr(settings, "asr_provider", "gemini")
    monkeypatch.setattr(gemini_asr, "is_configured", lambda: True)
    monkeypatch.setattr(xunfei_asr, "is_configured", lambda: False)
    assert _resolve_provider() == "gemini"


def test_resolve_provider_fallback_when_preferred_missing(monkeypatch):
    from app.config import settings
    from app.routers.asr import _resolve_provider

    # 偏好 xunfei 但只有 gemini 可用 → 回退到 gemini
    monkeypatch.setattr(settings, "asr_provider", "xunfei")
    monkeypatch.setattr(gemini_asr, "is_configured", lambda: True)
    monkeypatch.setattr(xunfei_asr, "is_configured", lambda: False)
    assert _resolve_provider() == "gemini"


def test_resolve_provider_none_when_nothing(monkeypatch):
    from app.config import settings
    from app.routers.asr import _resolve_provider

    monkeypatch.setattr(settings, "asr_provider", "none")
    monkeypatch.setattr(gemini_asr, "is_configured", lambda: False)
    monkeypatch.setattr(xunfei_asr, "is_configured", lambda: False)
    assert _resolve_provider() == "none"
