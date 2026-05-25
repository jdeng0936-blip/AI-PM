"""
app/models/audit_log_archive.py — 审计日志归档表

Stage 1 引入。结构与 audit_logs 主表完全一致,额外加 archived_at 记录归档时间。
由 services/scheduled_tasks.py::archive_old_audit_logs 每月 1 日 02:00 自动迁移
12 个月以上的审计记录,避免主表无限膨胀。

查询历史审计:UNION audit_logs + audit_logs_archive 即可。
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.base_mixin import BaseMixin


class AuditLogArchive(BaseMixin, Base):
    __tablename__ = "audit_logs_archive"

    # ── 与 audit_logs 完全一致的字段 ─────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)  # 沿用主表原 id,不重新生成
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="login | submit_report | change_password | admin_action"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, comment="客户端 IP")
    detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="附加信息 JSON")

    # ── 归档专属字段 ─────────────────────────────────────────────────
    archived_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="归档时间(scheduled_tasks 迁移本条记录时填入)",
    )

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供;
    #       归档时保留主表原值,不重置。

    def __repr__(self) -> str:
        return f"<AuditLogArchive user={self.user_id} action={self.action} archived={self.archived_at}>"
