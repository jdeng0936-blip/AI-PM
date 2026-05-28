"""
app/services/kpi_service.py — Phase 9 KPI 服务层

职责：
  - 列出 / Upsert KPI 目标（依赖 T-901-FIX 的 NULLS NOT DISTINCT UNIQUE）。
  - 复用 Phase 7 物化视图 mv_daily_user_stats / mv_weekly_dept_stats 计算达成率。

注意：
  - 所有 DB 入参一律 AsyncSession（pattern: from sqlalchemy.ext.asyncio import AsyncSession）。
  - 不引入 router 依赖；不在本文件里 raise HTTPException。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kpi_target import KpiMetric, KpiPeriod, KpiScope, KpiTarget
from app.models.user import User
from app.schemas.kpi import KpiAchievementResponse, KpiAchievementRow, KpiTargetIn, KpiTargetOut

AchievementStatus = Literal["on_track", "below_target", "no_data"]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _safe_divide(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _status_of(target: float, actual: float | None) -> AchievementStatus:
    if actual is None:
        return "no_data"

    achievement_rate = _safe_divide(actual, target)
    if achievement_rate is not None and achievement_rate >= 1:
        return "on_track"
    return "below_target"


async def _fetch_targets(db: AsyncSession, tenant_id: str, period: KpiPeriod | None = None) -> list[KpiTarget]:
    stmt = (
        select(KpiTarget)
        .where(KpiTarget.tenant_id == tenant_id)
        .order_by(KpiTarget.scope, KpiTarget.metric, KpiTarget.scope_value.nulls_first())
    )
    if period is not None:
        stmt = stmt.where(KpiTarget.period == period)

    return list((await db.execute(stmt)).scalars().all())


async def list_kpi_targets(db: AsyncSession, *, tenant_id: str) -> list[KpiTargetOut]:
    targets = await _fetch_targets(db, tenant_id)
    return [KpiTargetOut.model_validate(target) for target in targets]


async def upsert_kpi_target(
    db: AsyncSession,
    payload: KpiTargetIn,
    actor: User,
) -> KpiTargetOut:
    stmt = pg_insert(KpiTarget).values(
        scope=payload.scope,
        scope_value=payload.scope_value,
        metric=payload.metric,
        target_value=payload.target_value,
        period=payload.period,
        created_by=actor.id,
        tenant_id=actor.tenant_id,
    )
    upsert_stmt = stmt.on_conflict_do_update(
        constraint="uq_kpi_targets_scope_metric_period",
        set_={
            "target_value": stmt.excluded.target_value,
            "updated_at": func.now(),
        },
    ).returning(KpiTarget)

    target = (await db.execute(upsert_stmt)).scalar_one()
    return KpiTargetOut.model_validate(target)


async def _global_actuals(db: AsyncSession, *, tenant_id: str) -> dict[KpiMetric, float | None]:
    four_weeks_ago = date.today() - timedelta(weeks=4)
    thirty_days_ago = date.today() - timedelta(days=30)

    submit_rate = (
        await db.execute(
            text(
                """
                SELECT AVG(submitter_rate) AS actual_value
                FROM mv_weekly_dept_stats
                WHERE tenant_id = :tenant_id
                  AND week_start >= :since
                """
            ),
            {"tenant_id": tenant_id, "since": four_weeks_ago},
        )
    ).scalar_one_or_none()
    avg_score = (
        await db.execute(
            text(
                """
                SELECT AVG(avg_score) AS actual_value
                FROM mv_daily_user_stats
                WHERE tenant_id = :tenant_id
                  AND report_date >= :since
                """
            ),
            {"tenant_id": tenant_id, "since": thirty_days_ago},
        )
    ).scalar_one_or_none()

    return {
        KpiMetric.submit_rate: _float_or_none(submit_rate),
        KpiMetric.avg_score: _float_or_none(avg_score),
    }


async def _department_actuals(db: AsyncSession, *, tenant_id: str) -> dict[str, dict[KpiMetric, float | None]]:
    four_weeks_ago = date.today() - timedelta(weeks=4)
    rows = (
        (
            await db.execute(
                text(
                    """
                    SELECT
                        department,
                        AVG(submitter_rate) AS submit_rate,
                        AVG(avg_score) AS avg_score
                    FROM mv_weekly_dept_stats
                    WHERE tenant_id = :tenant_id
                      AND week_start >= :since
                    GROUP BY department
                    """
                ),
                {"tenant_id": tenant_id, "since": four_weeks_ago},
            )
        )
        .mappings()
        .all()
    )

    return {
        str(row["department"]): {
            KpiMetric.submit_rate: _float_or_none(row["submit_rate"]),
            KpiMetric.avg_score: _float_or_none(row["avg_score"]),
        }
        for row in rows
        if row["department"] is not None
    }


def _actual_for_target(
    target: KpiTargetOut,
    global_actuals: dict[KpiMetric, float | None],
    department_actuals: dict[str, dict[KpiMetric, float | None]],
) -> float | None:
    if target.metric not in (KpiMetric.submit_rate, KpiMetric.avg_score):
        return None

    if target.scope == KpiScope.global_:
        return global_actuals.get(target.metric)

    if target.scope == KpiScope.department and target.scope_value is not None:
        return department_actuals.get(target.scope_value, {}).get(target.metric)

    return None


async def calculate_kpi_achievement(
    db: AsyncSession,
    period: KpiPeriod = KpiPeriod.monthly,
    *,
    tenant_id: str,
) -> KpiAchievementResponse:
    targets = [KpiTargetOut.model_validate(target) for target in await _fetch_targets(db, tenant_id, period)]
    global_actuals = await _global_actuals(db, tenant_id=tenant_id)
    department_actuals = await _department_actuals(db, tenant_id=tenant_id)

    rows: list[KpiAchievementRow] = []
    for target in targets:
        actual = _actual_for_target(target, global_actuals, department_actuals)
        gap = actual - target.target_value if actual is not None else None
        ratio = _safe_divide(actual, target.target_value)
        achievement_rate = ratio * 100 if ratio is not None else None
        rows.append(
            KpiAchievementRow(
                scope=target.scope,
                scope_value=target.scope_value,
                metric=target.metric,
                period=target.period,
                target_value=target.target_value,
                actual_value=actual,
                gap=gap,
                achievement_rate=achievement_rate,
                status=_status_of(target.target_value, actual),
            )
        )

    return KpiAchievementResponse(period=period, snapshot_at=datetime.now(UTC), rows=rows)
