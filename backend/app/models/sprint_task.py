"""
app/models/sprint_task.py — Sprint 任务级数据

每个 Sprint 拆解为若干 SprintTask,故事点 + 状态 + 关联日报。
日报通过 mentioned_task_ids 关联到任务(由 AI 提取或手工指定)。

字段对齐白皮书 §5.2「Sprint 任务级管理」与 §5.4「燃尽图自动生成」。
"""
from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import (
    Boolean, Date, Enum, ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class TaskStatus(str, enum.Enum):
    todo        = "todo"         # 待开始
    in_progress = "in_progress"  # 进行中
    blocked     = "blocked"      # 阻塞
    done        = "done"         # 完成
    cancelled   = "cancelled"    # 取消


class TaskPriority(str, enum.Enum):
    p0 = "p0"  # 关键路径
    p1 = "p1"  # 高
    p2 = "p2"  # 中
    p3 = "p3"  # 低


class SprintTask(BaseMixin, Base):
    """Sprint 内的可执行任务"""
    __tablename__ = "sprint_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    sprint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sprints.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    # 可关联到 KR(从 KR.sprint_id 反向也能查到)
    kr_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("key_results.id", ondelete="SET NULL"), nullable=True,
    )
    assignee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    story_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.todo, index=True, nullable=False,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.p2, nullable=False,
    )

    # 关键路径标记(由 services/critical_path.py 自动更新,或手工指定)
    is_on_critical_path: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 依赖的其他 task ID(关键路径计算用)
    depends_on: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True,
        comment="依赖的 task UUID 字符串列表(简化:不做强外键约束,允许 dangling)",
    )

    planned_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    planned_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # 完成时的实际故事点(可能与估算不同)
    actual_story_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<SprintTask {self.title[:20]} {self.status} pts={self.story_points}>"


class BurndownSnapshot(BaseMixin, Base):
    """每日燃尽快照 — 用于绘制燃尽图(理想线 vs 实际线)"""
    __tablename__ = "burndown_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    sprint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sprints.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # 当日累计完成的故事点(已 done 任务的故事点之和)
    completed_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 当日剩余故事点 = 总计划 - 已完成
    remaining_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 总计划点(快照时刻,可能因加任务变化)
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 任务计数
    done_count: Mapped[int] = mapped_column(Integer, default=0)
    in_progress_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    todo_count: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return (
            f"<BurndownSnapshot sprint={self.sprint_id} {self.snapshot_date} "
            f"remaining={self.remaining_points}/{self.total_points}>"
        )
