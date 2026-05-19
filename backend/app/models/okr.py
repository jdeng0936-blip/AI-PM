"""
app/models/okr.py — OKR 战略对齐模型

OKR Cycle → Objective → Key Result → Sprint/Daily Report

实现白皮书第七章「战略增强层」：
  - OKR 三层结构：Objective（目标）→ Key Result（关键结果）
  - OKR Cycle 管理：季度/月度周期
  - KR 与 Sprint 绑定，Sprint 与日报绑定
"""
from __future__ import annotations

import uuid
import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Date,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.base_mixin import BaseMixin


class OKRCycleType(str, enum.Enum):
    quarterly = "quarterly"  # 季度 OKR
    monthly   = "monthly"    # 月度 OKR
    yearly    = "yearly"     # 年度 OKR


class OKRStatus(str, enum.Enum):
    draft     = "draft"      # 草稿
    active    = "active"     # 进行中
    completed = "completed"  # 已完成
    archived  = "archived"   # 已归档


class OKRCycle(BaseMixin, Base):
    """OKR 周期 — 一个季度/月度的 OKR 集合"""
    __tablename__ = "okr_cycles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="周期名称，如 2026Q2"
    )
    cycle_type: Mapped[OKRCycleType] = mapped_column(
        Enum(OKRCycleType), nullable=False, default=OKRCycleType.quarterly
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[OKRStatus] = mapped_column(
        Enum(OKRStatus), nullable=False, default=OKRStatus.draft
    )


class Objective(BaseMixin, Base):
    """战略目标 — 一个周期内的高层目标"""
    __tablename__ = "objectives"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("okr_cycles.id", ondelete="CASCADE"), nullable=False,
        comment="所属 OKR 周期"
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
        comment="关联项目（可选）"
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False,
        comment="目标负责人"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="目标标题"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="目标描述"
    )
    weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, comment="权重 0.0~1.0"
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="整体进度 0~100"
    )
    status: Mapped[OKRStatus] = mapped_column(
        Enum(OKRStatus), nullable=False, default=OKRStatus.active
    )


class KeyResult(BaseMixin, Base):
    """关键结果 — 量化可衡量的子目标"""
    __tablename__ = "key_results"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    objective_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False,
        comment="所属 Objective"
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False,
        comment="KR 负责人"
    )
    sprint_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True,
        comment="关联 Sprint（可选）"
    )
    title: Mapped[str] = mapped_column(
        String(300), nullable=False, comment="KR 标题"
    )
    metric_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="percentage",
        comment="度量类型: percentage / count / currency"
    )
    target_value: Mapped[float] = mapped_column(
        Float, nullable=False, default=100.0, comment="目标值"
    )
    current_value: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="当前值"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5,
        comment="信心指数 0.0~1.0（AI 可自动评估）"
    )

    # ── 单位与描述(便于 AI 提取时识别)──
    unit: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="单位:ms / % / 个 / 元 等"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="KR 详细描述,给 AI 抽取进度时提供上下文"
    )

    @property
    def progress(self) -> float:
        if self.target_value == 0:
            return 0.0
        return min(round(self.current_value / self.target_value * 100, 1), 100.0)


# ════════════════════════════════════════════════════════════════
# KR 进度变更日志 — 记录每次进度更新(AI 提取 / 手工修改)
# ════════════════════════════════════════════════════════════════


class KRProgressSource(str, enum.Enum):
    manual = "manual"          # 手工更新
    ai_extracted = "ai_extracted"  # AI 从日报提取
    sprint_close = "sprint_close"  # Sprint 关闭时聚合
    system = "system"          # 系统自动(如季度归档)


class KRProgressLog(BaseMixin, Base):
    """每次 KR 进度变更的审计日志"""
    __tablename__ = "kr_progress_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    kr_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("key_results.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="来源日报(AI 提取时记录)"
    )
    previous_value: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="变更前的值"
    )
    new_value: Mapped[float] = mapped_column(
        Float, nullable=False, comment="变更后的值"
    )
    source: Mapped[KRProgressSource] = mapped_column(
        Enum(KRProgressSource), nullable=False,
        default=KRProgressSource.manual, index=True,
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="AI 抽取的置信度 0~1"
    )
    note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="变更说明(AI 提取的依据 / 手工备注)"
    )

    def __repr__(self) -> str:
        return (
            f"<KRProgressLog kr={self.kr_id} {self.previous_value}→{self.new_value} "
            f"src={self.source}>"
        )
