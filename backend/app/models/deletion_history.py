"""
app/models/deletion_history.py — 软删除治理历史表

V2.6 将 V2.4/V2.5 分散的 deleted_at 软删动作收敛到统一治理层。
一条记录对应一次批量软删,用于后续"我的最近删除"、批量恢复和 30 天清理 dry-run。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class DeletionHistory(BaseMixin, Base):
    """一次软删批次的治理记录。"""

    __tablename__ = "deletion_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="执行软删的用户;系统任务可为空",
    )
    table_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="被软删记录所在业务表名",
    )
    record_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="本次批量软删命中的 UUID 列表(JSONB array,字符串形式)",
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="软删发生时间",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="默认 deleted_at + 30 days;过期后进入硬删清理候选",
    )
    restored_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="该删除批次被恢复的时间",
    )
    restored_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="执行恢复的用户",
    )
    hard_deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="过期硬删清理完成时间",
    )

    def __repr__(self) -> str:
        count = len(self.record_ids)
        return f"<DeletionHistory table={self.table_name} count={count} deleted_at={self.deleted_at}>"
