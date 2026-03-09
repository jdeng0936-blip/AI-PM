"""
app/routers/okr.py — OKR 战略对齐 API

CRUD for OKR Cycles, Objectives, Key Results.
支持 KR 进度自动从日报中提取更新。
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role, get_current_user
from app.models.okr import OKRCycle, Objective, KeyResult, OKRStatus
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/okr", tags=["OKR"])


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════

class CycleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    cycle_type: str = "quarterly"
    start_date: str
    end_date: str

class ObjectiveCreate(BaseModel):
    cycle_id: str
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    project_id: Optional[str] = None
    weight: float = 1.0

class KRCreate(BaseModel):
    objective_id: str
    title: str = Field(..., min_length=1, max_length=300)
    sprint_id: Optional[str] = None
    metric_type: str = "percentage"
    target_value: float = 100.0

class KRUpdate(BaseModel):
    current_value: Optional[float] = None
    confidence: Optional[float] = None


# ═══════════════════════════════════════════════════════════════════
# Cycle CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("/cycles")
async def list_cycles(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """列出所有 OKR 周期"""
    result = await db.execute(
        select(OKRCycle).order_by(OKRCycle.start_date.desc())
    )
    cycles = result.scalars().all()
    return [
        {
            "id": str(c.id), "name": c.name,
            "cycle_type": c.cycle_type.value if hasattr(c.cycle_type, 'value') else c.cycle_type,
            "start_date": str(c.start_date), "end_date": str(c.end_date),
            "status": c.status.value if hasattr(c.status, 'value') else c.status,
        }
        for c in cycles
    ]


@router.post("/cycles")
async def create_cycle(
    req: CycleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    """创建 OKR 周期"""
    from datetime import date as date_type
    cycle = OKRCycle(
        name=req.name,
        cycle_type=req.cycle_type,
        start_date=date_type.fromisoformat(req.start_date),
        end_date=date_type.fromisoformat(req.end_date),
        created_by=user.id,
    )
    db.add(cycle)
    await db.commit()
    return {"id": str(cycle.id), "message": f"OKR 周期「{req.name}」已创建"}


# ═══════════════════════════════════════════════════════════════════
# Objective CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("/objectives")
async def list_objectives(
    cycle_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出目标"""
    stmt = select(Objective)
    if cycle_id:
        stmt = stmt.where(Objective.cycle_id == uuid.UUID(cycle_id))
    stmt = stmt.order_by(Objective.weight.desc())
    result = await db.execute(stmt)
    objs = result.scalars().all()
    return [
        {
            "id": str(o.id), "cycle_id": str(o.cycle_id),
            "title": o.title, "description": o.description,
            "weight": o.weight, "progress": o.progress,
            "status": o.status.value if hasattr(o.status, 'value') else o.status,
        }
        for o in objs
    ]


@router.post("/objectives")
async def create_objective(
    req: ObjectiveCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """创建战略目标"""
    obj = Objective(
        cycle_id=uuid.UUID(req.cycle_id),
        owner_id=user.id,
        title=req.title,
        description=req.description,
        project_id=uuid.UUID(req.project_id) if req.project_id else None,
        weight=req.weight,
        created_by=user.id,
    )
    db.add(obj)
    await db.commit()
    return {"id": str(obj.id), "message": f"目标「{req.title}」已创建"}


# ═══════════════════════════════════════════════════════════════════
# Key Result CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("/key-results")
async def list_key_results(
    objective_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """列出关键结果"""
    stmt = select(KeyResult)
    if objective_id:
        stmt = stmt.where(KeyResult.objective_id == uuid.UUID(objective_id))
    result = await db.execute(stmt)
    krs = result.scalars().all()
    return [
        {
            "id": str(kr.id), "objective_id": str(kr.objective_id),
            "title": kr.title, "metric_type": kr.metric_type,
            "target_value": kr.target_value, "current_value": kr.current_value,
            "progress": kr.progress, "confidence": kr.confidence,
        }
        for kr in krs
    ]


@router.post("/key-results")
async def create_key_result(
    req: KRCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """创建关键结果"""
    kr = KeyResult(
        objective_id=uuid.UUID(req.objective_id),
        owner_id=user.id,
        title=req.title,
        sprint_id=uuid.UUID(req.sprint_id) if req.sprint_id else None,
        metric_type=req.metric_type,
        target_value=req.target_value,
        created_by=user.id,
    )
    db.add(kr)
    await db.commit()
    return {"id": str(kr.id), "message": f"KR「{req.title}」已创建"}


@router.patch("/key-results/{kr_id}")
async def update_key_result(
    kr_id: str,
    req: KRUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """更新 KR 进度"""
    result = await db.execute(
        select(KeyResult).where(KeyResult.id == uuid.UUID(kr_id))
    )
    kr = result.scalar_one_or_none()
    if not kr:
        raise HTTPException(404, "KR 不存在")

    if req.current_value is not None:
        kr.current_value = req.current_value
    if req.confidence is not None:
        kr.confidence = req.confidence

    await db.commit()

    # 自动更新所属 Objective 的 progress
    kr_result = await db.execute(
        select(KeyResult).where(KeyResult.objective_id == kr.objective_id)
    )
    all_krs = kr_result.scalars().all()
    if all_krs:
        obj = await db.get(Objective, kr.objective_id)
        if obj:
            obj.progress = round(sum(k.progress for k in all_krs) / len(all_krs), 1)
            await db.commit()

    return {"message": "KR 已更新", "progress": kr.progress}
