"""
app/routers/asr.py — 语音转写端点

端点:
- POST /asr/transcribe   接收音频文件 → 上传到 OSS → 讯飞 ASR → 落库 Attachment + transcript
- GET  /asr/status       查询 ASR 配置状态(前端用来决定是否显示录音按钮)

输入约束:
- 推荐 16kHz / 16bit / mono PCM 或 WAV;其他格式会原样发给讯飞,可能识别失败
- 文件大小 ≤ 10MB(约 5 分钟)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user
from app.models.attachment import Attachment, AttachmentKind
from app.models.user import User
from app.services import gemini_asr, oss_service, xunfei_asr

logger = logging.getLogger("aipm.asr_router")

router = APIRouter(prefix="/api/v1/asr", tags=["语音转写"])

MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB


def _resolve_provider() -> str:
    """选择当前可用的 ASR 实现"""
    from app.config import settings

    p = (settings.asr_provider or "").lower()
    if p == "gemini" and gemini_asr.is_configured():
        return "gemini"
    if p == "xunfei" and xunfei_asr.is_configured():
        return "xunfei"
    # 自动回退:有谁可用就用谁
    if gemini_asr.is_configured():
        return "gemini"
    if xunfei_asr.is_configured():
        return "xunfei"
    return "none"


class TranscribeResponse(BaseModel):
    attachment_id: Optional[str] = None
    file_url: Optional[str] = None
    transcript: Optional[str]
    provider: str
    configured: bool


class AsrStatusResponse(BaseModel):
    configured: bool
    provider: str


@router.get("/status", response_model=AsrStatusResponse)
async def asr_status(_: User = Depends(get_current_user)):
    """前端调用判断是否可用"""
    provider = _resolve_provider()
    return AsrStatusResponse(
        configured=provider != "none",
        provider=provider,
    )


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    save_attachment: bool = Form(default=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    上传音频文件 → 讯飞 ASR 转写 → 返回文本(+ 可选落库为 Attachment)。

    save_attachment=False 时只转写,不持久化文件(适合「即说即填」场景)。
    """
    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(400, "音频文件为空")
    if len(raw) > MAX_AUDIO_SIZE:
        raise HTTPException(413, f"音频超过 {MAX_AUDIO_SIZE // (1024 * 1024)}MB 上限")

    # 1) 调 ASR(按 provider 路由)
    provider = _resolve_provider()
    transcript: Optional[str] = None
    file_name_for_asr = file.filename or "voice.wav"
    mime_type_for_asr = file.content_type or "audio/wav"

    if provider == "gemini":
        transcript = await gemini_asr.transcribe(
            raw,
            file_name=file_name_for_asr,
            mime_type=mime_type_for_asr,
        )
    elif provider == "xunfei":
        transcript = await xunfei_asr.transcribe(raw)
    configured = provider != "none"

    # 2) 落库附件(可选)
    attachment_id: Optional[str] = None
    file_url: Optional[str] = None
    if save_attachment:
        file_name = file.filename or "voice.wav"
        mime_type = file.content_type or "audio/wav"
        storage_key = oss_service.make_storage_key(
            kind="voice",
            user_id=str(current_user.id),
            file_name=file_name,
        )
        file_url = await oss_service.upload_bytes(storage_key, raw, mime_type)

        attachment = Attachment(
            uploaded_by=current_user.id,
            related_report_id=None,
            kind=AttachmentKind.voice,
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=len(raw),
            storage_key=storage_key,
            file_url=file_url,
            transcript=transcript,
        )
        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)
        attachment_id = str(attachment.id)

    return TranscribeResponse(
        attachment_id=attachment_id,
        file_url=file_url,
        transcript=transcript,
        provider=provider,
        configured=configured,
    )
