"""
app/models/project_followup.py — 项目跟进记录时间轴

T-1106: 轻量 append-only 跟进记录。主干项目与临时工单共享该表,
临时工单健康度会读取最近一条 followup 的 created_at 做 stale 判断。
"""

import uuid

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class ProjectFollowUp(BaseMixin, Base):
    __tablename__ = "project_follow_ups"
    __table_args__ = (
        Index(
            "ix_project_follow_ups_project_created",
            "project_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<ProjectFollowUp project={self.project_id} created_at={self.created_at}>"
