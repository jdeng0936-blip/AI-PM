"""
app/schemas/kpi.py — Phase 9 KPI 目标与达成率 Pydantic V2 Schemas

参考已落地的 ORM Model（app/models/kpi_target.py）字段约束：
  - scope ∈ {global, department, job_title}
  - scope_value 可空（global 模式必空，其他模式必填）
  - metric ∈ {submit_rate, avg_score, blocker_resolve_days, objective_completion}
  - period ∈ {weekly, monthly, quarterly}
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.kpi_target import KpiMetric, KpiPeriod, KpiScope


class KpiTargetIn(BaseModel):
    scope: KpiScope
    scope_value: str | None = Field(None, max_length=50)
    metric: KpiMetric
    target_value: float = Field(..., gt=0)
    period: KpiPeriod = KpiPeriod.monthly

    @model_validator(mode="after")
    def validate_scope_value(self) -> Self:
        if self.scope == KpiScope.global_:
            if self.scope_value is not None:
                raise ValueError("scope=global 时 scope_value 必须为 None")
            return self

        if self.scope_value is None or not self.scope_value.strip():
            raise ValueError("非 global scope 时 scope_value 必须非空")

        self.scope_value = self.scope_value.strip()
        return self


class KpiTargetOut(BaseModel):
    id: int
    scope: KpiScope
    scope_value: str | None
    metric: KpiMetric
    target_value: float
    period: KpiPeriod
    created_at: datetime | None
    updated_at: datetime | None
    created_by: uuid.UUID | None
    tenant_id: str

    model_config = ConfigDict(from_attributes=True)


class KpiAchievementRow(BaseModel):
    scope: KpiScope
    scope_value: str | None
    metric: KpiMetric
    period: KpiPeriod
    target_value: float
    actual_value: float | None
    gap: float | None
    achievement_rate: float | None
    status: Literal["on_track", "below_target", "no_data"]


class KpiAchievementResponse(BaseModel):
    period: KpiPeriod
    snapshot_at: datetime
    rows: list[KpiAchievementRow]
