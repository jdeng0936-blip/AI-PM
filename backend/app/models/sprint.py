"""
app/models/sprint.py — 软件轨 Sprint 表（敏捷冲刺）

Sprint 是软件轨在"双轨并行开发期（Stage 3）"内的迭代单元。
默认周期 14 天（2周），由项目负责人可自定义。

retrospective JSONB 结构（Sprint 回顾三问）：
{
  "went_well":    ["代码评审效率高", "接口联调顺畅"],
  "improve":      ["单元测试覆盖率不足"],
  "action_items": [{"item": "提高测试覆盖到80%", "owner": "张毅", "due": "2026-04-01"}]
}
"""
import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.base_mixin import BaseMixin


class SprintStatus(str, enum.Enum):
    planning  = "planning"   # 规划中（未开始）
    active    = "active"     # 进行中
    completed = "completed"  # 已完成（含回顾）


class Sprint(BaseMixin, Base):
    __tablename__ = "sprints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # 通常归属于 Stage 3（双轨并行开发期），但也可能延伸
    stage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("project_stages.id", ondelete="SET NULL"), nullable=True
    )

    sprint_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3...
    goal: Mapped[Optional[str]] = mapped_column(Text)   # Sprint 目标（1-2句话）

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # 由该 Sprint 期间所有软件轨成员日报的 ai_score 聚合
    health_score: Mapped[int] = mapped_column(Integer, default=100)

    # Story Points（可选，工程师填报或 AI 估算）
    planned_story_points: Mapped[int] = mapped_column(Integer, default=0)
    completed_story_points: Mapped[int] = mapped_column(Integer, default=0)  # velocity

    # Sprint 回顾（完成后填写）
    retrospective: Mapped[Optional[dict]] = mapped_column(JSONB)

    status: Mapped[SprintStatus] = mapped_column(Enum(SprintStatus), default=SprintStatus.planning)

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<Sprint #{self.sprint_number} status={self.status} score={self.health_score}>"
