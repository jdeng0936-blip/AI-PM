"""
app/models/daily_supervised_task.py — 督导追踪溯源关联(T-1301)

桥接晚复核未完成任务、项目跟进 ProjectFollowUp 与次日晨规划顶置。
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class SupervisedStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class DailySupervisedTask(BaseMixin, Base):
    __tablename__ = "daily_supervised_tasks"
    __table_args__ = (
        Index(
            "ix_daily_supervised_tasks_user_status_active",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_daily_supervised_tasks_project_status",
            "project_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="被督导用户(从晚复核行的 user_id 继承)",
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        comment="督导所属项目(若晚复核行带 project_id 则继承;否则 NULL)",
    )
    sprint_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sprint_tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="督导关联的 Sprint 任务(若晚复核行带 sprint_task_id 则继承)",
    )
    source_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="触发督导的晚复核日报 ID(evening_review 行)",
    )
    project_followup_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("project_follow_ups.id", ondelete="SET NULL"),
        nullable=True,
        comment="同步写入的 ProjectFollowUp 跟进记录 ID(T-1106 表;允许 NULL 兼容补录场景)",
    )
    status: Mapped[SupervisedStatus] = mapped_column(
        Enum(SupervisedStatus, name="supervised_status", native_enum=True),
        default=SupervisedStatus.open,
        server_default="open",
        nullable=False,
        index=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="闭环时间;非 NULL ↔ status=closed",
    )
    closed_by_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"),
        nullable=True,
        comment="闭环触发的日报 ID(后续某次晚复核或晨规划完成同一任务)",
    )

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<DailySupervisedTask user={self.user_id} status={self.status.value} source={self.source_report_id}>"
