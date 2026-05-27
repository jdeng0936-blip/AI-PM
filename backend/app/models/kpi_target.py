"""
app/models/kpi_target.py — Phase 9 KPI 目标设定模型

用于持久化全局 / 部门 / 岗位维度的 KPI 目标。设计上保留
implementation-plan §9 的 SERIAL 风格自增整型主键；created_by 按本项目真实
users.id 类型校正为 UUID 外键；created_at / updated_at / created_by / tenant_id
统一由 BaseMixin 注入,避免重复声明通用字段。
"""

from __future__ import annotations

import enum
from typing import Optional

from sqlalchemy import Enum, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class KpiScope(str, enum.Enum):
    global_ = "global"
    department = "department"
    job_title = "job_title"


class KpiMetric(str, enum.Enum):
    submit_rate = "submit_rate"
    avg_score = "avg_score"
    sprint_completion = "sprint_completion"
    blocker_resolve_days = "blocker_resolve_days"


class KpiPeriod(str, enum.Enum):
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"


class KpiTarget(BaseMixin, Base):
    __tablename__ = "kpi_targets"
    __table_args__ = (
        UniqueConstraint("scope", "scope_value", "metric", "period", name="uq_kpi_targets_scope_metric_period"),
        Index("ix_kpi_targets_scope_metric", "scope", "metric"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[KpiScope] = mapped_column(
        Enum(KpiScope, name="kpi_scope", values_callable=_enum_values),
        nullable=False,
    )
    scope_value: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metric: Mapped[KpiMetric] = mapped_column(
        Enum(KpiMetric, name="kpi_metric", values_callable=_enum_values),
        nullable=False,
    )
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[KpiPeriod] = mapped_column(
        Enum(KpiPeriod, name="kpi_period", values_callable=_enum_values),
        nullable=False,
        default=KpiPeriod.monthly,
    )

    def __repr__(self) -> str:
        return f"<KpiTarget {self.scope.value}:{self.scope_value or '-'} / {self.metric.value} = {self.target_value}>"
