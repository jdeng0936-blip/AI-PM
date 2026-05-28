"""
app/routers/attachments.py — 附件上传/查询/下载

端点:
- POST   /attachments/upload            上传文件(后端代传,简单稳定)
- GET    /attachments/                  列出当前用户的附件
- GET    /attachments/by-report/{id}    某份日报的附件
- GET    /attachments/{id}/presigned    生成临时访问 URL(private bucket)
- GET    /attachments/local/{path:path} 本地降级文件代理下载
- DELETE /attachments/{id}              删除附件(仅上传者本人或 admin)

设计:
- 大小限制 25MB(图片/语音/PDF 都足够)
- 按 mime_type 自动分类为 image/voice/document/other
- 上传后只返回元数据 + URL,具体业务关联由日报提交时携带 attachment_ids 完成
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user
from app.models.attachment import Attachment, AttachmentKind
from app.models.daily_report import DailyReport
from app.models.user import User, UserRole
from app.services import oss_service

router = APIRouter(prefix="/api/v1/attachments", tags=["附件"])

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB
OFFICE_MIME_BY_EXT = {
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
SAFE_TEXT_EXTENSIONS = {".txt", ".csv", ".md", ".log"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".amr", ".ogg", ".webm"}
DANGEROUS_MIME_TYPES = {
    "image/svg+xml",
    "text/html",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
    "application/javascript",
    "text/javascript",
}
DANGEROUS_TEXT_MARKERS = (b"<script", b"<html", b"<!doctype", b"<?xml", b"<svg")


# ────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────


class AttachmentOut(BaseModel):
    id: UUID
    uploaded_by: UUID
    related_report_id: Optional[UUID]
    kind: str
    file_name: str
    mime_type: str
    size_bytes: int
    file_url: str
    transcript: Optional[str]
    duration_ms: Optional[int]
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class AttachmentListResponse(BaseModel):
    total: int
    items: list[AttachmentOut]


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────


# V2.5 Stage 1 Fix #1:对象级越权防御 — 三个 GET 端点共用 owner / admin 校验
# admin / manager 可读任意附件;其他用户只能读自己上传的或自己日报关联的附件
async def _check_attachment_access(
    db: AsyncSession,
    record: Attachment,
    current_user: User,
) -> None:
    """校验当前用户是否有权读取该附件;无权限抛 403。"""
    if current_user.role in (UserRole.admin, UserRole.manager):
        return
    if record.uploaded_by == current_user.id:
        return
    # 通过 related_report_id 反向校验日报归属
    if record.related_report_id is not None:
        report = await db.get(DailyReport, record.related_report_id)
        if report is not None and report.user_id == current_user.id:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该附件")


def _classify(mime_type: str, file_name: str) -> AttachmentKind:
    mt = (mime_type or "").lower()
    if mt.startswith("image/"):
        return AttachmentKind.image
    if mt.startswith("audio/") or mt in ("application/ogg",):
        return AttachmentKind.voice
    if mt in ("application/pdf",) or mt.startswith("text/") or mt.startswith("application/vnd."):
        return AttachmentKind.document
    # 用扩展名兜底
    ext = Path(file_name).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return AttachmentKind.image
    if ext in {".mp3", ".wav", ".m4a", ".amr", ".ogg", ".webm"}:
        return AttachmentKind.voice
    if ext in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}:
        return AttachmentKind.document
    return AttachmentKind.other


def _detect_safe_mime_type(raw: bytes, file_name: str, declared_type: str | None) -> str:
    """用文件头和扩展名做最小 MIME 嗅探，拒绝同源脚本类附件。"""
    ext = Path(file_name).suffix.lower()
    declared = (declared_type or "").split(";", 1)[0].strip().lower()
    if declared in DANGEROUS_MIME_TYPES:
        raise HTTPException(415, "不支持上传 HTML/SVG/XML/JavaScript 等可执行内容")

    lowered_head = raw[:512].lstrip().lower()
    if any(marker in lowered_head for marker in DANGEROUS_TEXT_MARKERS):
        raise HTTPException(415, "不支持上传可能执行脚本的文本内容")

    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"%PDF-"):
        return "application/pdf"
    if raw.startswith(b"PK\x03\x04") and ext in OFFICE_MIME_BY_EXT:
        return OFFICE_MIME_BY_EXT[ext]
    if raw.startswith(b"\xd0\xcf\x11\xe0") and ext in OFFICE_MIME_BY_EXT:
        return OFFICE_MIME_BY_EXT[ext]
    if ext in AUDIO_EXTENSIONS and (declared.startswith("audio/") or declared == "application/ogg"):
        return declared
    if ext in SAFE_TEXT_EXTENSIONS:
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "文本附件必须使用 UTF-8 编码")
        return mimetypes.guess_type(file_name)[0] or "text/plain"

    raise HTTPException(415, "不支持的附件类型")


async def _check_report_link_access(
    db: AsyncSession,
    related_report_id: Optional[UUID],
    current_user: User,
) -> None:
    """上传时校验附件关联的日报存在且当前用户有权挂载。"""
    if related_report_id is None:
        return
    report = await db.get(DailyReport, related_report_id)
    if report is None or report.deleted_at is not None:
        raise HTTPException(404, "日报不存在")
    if current_user.role not in (UserRole.admin, UserRole.manager) and report.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权关联他人日报")


# ────────────────────────────────────────────────────────────────
# 上传
# ────────────────────────────────────────────────────────────────


@router.post("/upload", response_model=AttachmentOut)
async def upload_attachment(
    file: UploadFile = File(...),
    related_report_id: Optional[UUID] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传一个附件文件到 OSS(未配置时本地降级)"""
    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(400, "文件为空")
    if len(raw) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"文件超过 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB 上限")

    file_name = file.filename or "unnamed"
    await _check_report_link_access(db, related_report_id, current_user)

    mime_type = _detect_safe_mime_type(raw, file_name, file.content_type)
    kind = _classify(mime_type, file_name)

    storage_key = oss_service.make_storage_key(
        kind=kind.value,
        user_id=str(current_user.id),
        file_name=file_name,
    )
    file_url = await oss_service.upload_bytes(storage_key, raw, mime_type)

    record = Attachment(
        uploaded_by=current_user.id,
        related_report_id=related_report_id,
        kind=kind,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=len(raw),
        storage_key=storage_key,
        file_url=file_url,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return AttachmentOut(
        id=record.id,
        uploaded_by=record.uploaded_by,
        related_report_id=record.related_report_id,
        kind=record.kind.value,
        file_name=record.file_name,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        file_url=record.file_url,
        transcript=record.transcript,
        duration_ms=record.duration_ms,
        created_at=record.created_at.isoformat() if record.created_at else None,
    )


# ────────────────────────────────────────────────────────────────
# 查询
# ────────────────────────────────────────────────────────────────


@router.get("/", response_model=AttachmentListResponse)
async def list_my_attachments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    kind: Optional[AttachmentKind] = None,
):
    """列出当前用户的附件。管理层可看全部(?owner_id=...)留待后续扩展。"""
    q = select(Attachment)
    if current_user.role == UserRole.employee:
        q = q.where(Attachment.uploaded_by == current_user.id)
    if kind:
        q = q.where(Attachment.kind == kind)

    total_q = q.with_only_columns(Attachment.id)
    total = len((await db.execute(total_q)).scalars().all())

    q = q.order_by(desc(Attachment.created_at)).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    items = [
        AttachmentOut(
            id=r.id,
            uploaded_by=r.uploaded_by,
            related_report_id=r.related_report_id,
            kind=r.kind.value,
            file_name=r.file_name,
            mime_type=r.mime_type,
            size_bytes=r.size_bytes,
            file_url=r.file_url,
            transcript=r.transcript,
            duration_ms=r.duration_ms,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return AttachmentListResponse(total=total, items=items)


@router.get("/by-report/{report_id}", response_model=list[AttachmentOut])
async def list_attachments_by_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V2.5 Stage 1 Fix #1:校验报告归属 — 避免知道 report_id 就能列出附件
    report = await db.get(DailyReport, report_id)
    if report is None:
        raise HTTPException(404, "日报不存在")
    if current_user.role not in (UserRole.admin, UserRole.manager) and report.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看他人日报附件")

    rows = (await db.execute(select(Attachment).where(Attachment.related_report_id == report_id))).scalars().all()
    return [
        AttachmentOut(
            id=r.id,
            uploaded_by=r.uploaded_by,
            related_report_id=r.related_report_id,
            kind=r.kind.value,
            file_name=r.file_name,
            mime_type=r.mime_type,
            size_bytes=r.size_bytes,
            file_url=r.file_url,
            transcript=r.transcript,
            duration_ms=r.duration_ms,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


@router.get("/{attachment_id}/presigned")
async def presigned_url(
    attachment_id: UUID,
    expires: int = Query(3600, ge=60, le=86400),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = await db.get(Attachment, attachment_id)
    if not record:
        raise HTTPException(404, "附件不存在")

    # V2.5 Stage 1 Fix #1:对象级越权防御
    await _check_attachment_access(db, record, current_user)

    url = oss_service.generate_presigned_url(record.storage_key, expires)
    if not url:
        # 未配置 OSS 或失败 → 直接返回 file_url(本地代理)
        return {"url": record.file_url, "expires_in": expires, "fallback": True}
    return {"url": url, "expires_in": expires, "fallback": False}


# ────────────────────────────────────────────────────────────────
# 本地降级:静态文件代理
# ────────────────────────────────────────────────────────────────


@router.get("/local/{path:path}")
async def serve_local_file(
    path: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """OSS 未配置时,通过后端读取本地降级目录里的文件。

    V2.5 Stage 1 Fix #1:不再只校验"已登录"。先反查 Attachment.storage_key,
    确认 attachment 存在 + 当前用户有权访问,再读文件。
    返回 404(而非 403)给"无对应附件 / 无权访问"两种情况,避免泄露路径存在性。
    """
    # 通过 storage_key 反查附件归属
    record = (await db.execute(select(Attachment).where(Attachment.storage_key == path))).scalar_one_or_none()
    if record is None:
        raise HTTPException(404, "文件不存在")
    try:
        await _check_attachment_access(db, record, current_user)
    except HTTPException:
        # 越权 → 也返回 404 而非 403(避免泄露文件存在性)
        raise HTTPException(404, "文件不存在")

    data = oss_service.read_local_file(path)
    if data is None:
        raise HTTPException(404, "文件不存在")
    safe_download_name = Path(record.file_name).name.replace('"', "_")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_download_name}"',
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=data, media_type=record.mime_type or "application/octet-stream", headers=headers)


# ────────────────────────────────────────────────────────────────
# 删除
# ────────────────────────────────────────────────────────────────


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = await db.get(Attachment, attachment_id)
    if not record:
        raise HTTPException(404, "附件不存在")
    if record.uploaded_by != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(403, "无权删除他人附件")

    await oss_service.delete(record.storage_key)
    await db.delete(record)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
