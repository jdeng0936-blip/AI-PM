"""
app/models/capacity.py — 资源负载水位模型

CapacitySnapshot:每人每 Sprint 的容量水位快照
  - 用于审计 + 时间序列分析
  - 由 services/capacity_engine 周期性写入(每周一 + 任务变更触发)

字段对齐白皮书 §7.2「资源负载水位与瓶颈预判」。
"""
from __future__ import annotations

import enum
import uuid
from typing import Optional

from sqlalchemy import (
    Enum as SAEnum, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class CapacityLevel(str, enum.Enum):
    """水位等级 — 与前端颜色映射"""
    idle      = "idle"        # 占用 < 30%(显著闲置)
    healthy   = "healthy"     # 30% ≤ 占用 < 80%(健康)
    high      = "high"        # 80% ≤ 占用 < 100%(高位但未爆)
    overload  = "overload"    # 占用 ≥ 100%(过载,需调配)


class CapacitySnapshot(BaseMixin, Base):
    """每人每 Sprint 的容量水位快照"""
    __tablename__ = "capacity_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    sprint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sprints.id", ondelete="CASCADE"), index=True, nullable=False,
    )

    # 用户基础容量(取自 User.story_points_capacity,可能被 velocity 调整)
    base_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    # 真实有效容量(可能因休假/出差等折减)
    effective_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=8)

    # 已分配点数:assignee=该用户 的所有 active task(todo + in_progress + blocked)的故事点之和
    allocated_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 已完成点数:done 状态任务的实际故事点
    completed_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 任务数(用于额外维度判定:任务过多 = 切换成本高)
    active_task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked_task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_path_task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 占用率 = allocated / effective_capacity(0-2.0,>1 即过载)
    utilization: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    level: Mapped[CapacityLevel] = mapped_column(
        SAEnum(CapacityLevel), default=CapacityLevel.healthy, nullable=False, index=True,
    )

    # 历史 velocity 调整系数(实际能力 / 标称容量,可用来微调 effective_capacity)
    velocity_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # 调配建议(JSON 字符串便于灵活扩展,内容如「建议把 task_x 转给 user_y」)
    suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<CapacitySnapshot user={self.user_id} sprint={self.sprint_id} "
            f"util={self.utilization:.0%} {self.level.value}>"
        )
