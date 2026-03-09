"""
app/models/audit_log.py — 操作审计日志表
记录登录、关键操作等审计信息。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class AuditLog(BaseMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="login | submit_report | change_password | admin_action"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True, comment="客户端 IP"
    )
    detail: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, comment="附加信息 JSON"
    )

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<AuditLog user={self.user_id} action={self.action}>"
