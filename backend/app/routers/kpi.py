"""
app/routers/kpi.py — Phase 9 KPI 目标管理与达成率 API

三端点:
  - GET  /api/v1/admin/kpi/             —— 列出 KPI 目标
  - POST /api/v1/admin/kpi/             —— 创建/更新 KPI 目标 (upsert)
  - GET  /api/v1/admin/kpi/achievement  —— 计算达成率快照

RBAC: admin + manager;普通员工 403。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.kpi_target import KpiPeriod
from app.models.user import User, UserRole
from app.schemas.kpi import KpiAchievementResponse, KpiTargetIn, KpiTargetOut
from app.services.kpi_service import calculate_kpi_achievement, list_kpi_targets, upsert_kpi_target

router = APIRouter(prefix="/api/v1/admin/kpi", tags=["KPI"])
_mgr_or_admin = require_role(UserRole.admin, UserRole.manager)


@router.get("/", response_model=list[KpiTargetOut])
async def list_targets(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> list[KpiTargetOut]:
    return await list_kpi_targets(db, tenant_id=_user.tenant_id)


@router.post("/", response_model=KpiTargetOut, status_code=status.HTTP_200_OK)
async def upsert_target(
    payload: KpiTargetIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(_mgr_or_admin),
) -> KpiTargetOut:
    return await upsert_kpi_target(db, payload, actor)


@router.get("/achievement", response_model=KpiAchievementResponse)
async def get_achievement(
    period: KpiPeriod = Query(default=KpiPeriod.monthly, description="weekly/monthly/quarterly"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> KpiAchievementResponse:
    return await calculate_kpi_achievement(db, period, tenant_id=_user.tenant_id)
