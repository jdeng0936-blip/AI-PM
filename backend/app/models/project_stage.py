"""
app/models/project_stage.py — IPD 阶段表

每个项目自动初始化 5 个阶段：
  1. 概念与立项期 (Concept & Charter)
  2. 计划与设计期 (Plan & Design)
  3. 双轨并行开发期 (Dual-Track Development) ← AI-PM 日报主战场
  4. 集成与测试期 (Integration & Qualify)
  5. 量产与交付期 (Launch & Delivery)

milestones JSONB 结构示例（硬件轨）：
[
  {"name": "原理图评审", "planned_date": "2026-03-01", "actual_date": null, "status": "pending"},
  {"name": "PCB打样送厂", "planned_date": "2026-03-15", "actual_date": "2026-03-16", "status": "done"},
  {"name": "贴片组装完成", "planned_date": "2026-04-01", "actual_date": null, "status": "blocked"}
]
"""
import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.base_mixin import BaseMixin


class StageTrack(str, enum.Enum):
    hardware = "hardware"
    software = "software"
    both     = "both"      # 联调阶段双轨合并


class StageHealthStatus(str, enum.Enum):
    green  = "green"
    yellow = "yellow"
    red    = "red"
    locked = "locked"  # 前置关卡未通过，本阶段锁定


# IPD 5 阶段定义（name, track, typical_duration_days）
STAGE_DEFINITIONS = [
    (1, "概念与立项期",     "both",     14),
    (2, "计划与设计期",     "both",     21),
    (3, "双轨并行开发期",   "both",    60),
    (4, "集成与测试期",     "both",     21),
    (5, "量产与交付期",     "both",     14),
]


class ProjectStage(BaseMixin, Base):
    __tablename__ = "project_stages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )

    stage_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    track: Mapped[StageTrack] = mapped_column(Enum(StageTrack), default=StageTrack.both)

    # 时间节点
    planned_start: Mapped[Optional[date]] = mapped_column(Date)
    planned_end: Mapped[Optional[date]] = mapped_column(Date)
    actual_start: Mapped[Optional[date]] = mapped_column(Date)
    actual_end: Mapped[Optional[date]] = mapped_column(Date)

    # 健康度（由 health_engine.py 基于阶段内成员日报自动更新）
    health_status: Mapped[StageHealthStatus] = mapped_column(
        Enum(StageHealthStatus), default=StageHealthStatus.green
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)     # 0-100
    health_score: Mapped[int] = mapped_column(Integer, default=100)   # 0-100

    # 里程碑节点（硬件轨核心）
    milestones: Mapped[Optional[list]] = mapped_column(JSONB, default=list)

    # 该阶段对应的 Gate 是否已通过
    gate_passed: Mapped[bool] = mapped_column(default=False)
    gate_passed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<ProjectStage stage={self.stage_number} health={self.health_status} progress={self.progress_pct}%>"
