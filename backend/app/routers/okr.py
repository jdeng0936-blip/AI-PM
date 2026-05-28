"""
app/routers/okr.py — OKR 战略对齐 API

CRUD for OKR Cycles, Objectives, Key Results + KR 进度变更日志。

权限:
- list_* / tree / progress-logs:任何登录用户可看(战略透明)
- create / update / delete:admin + manager

进度变更原则:
- 任何 KR.current_value 的写入都必须写入 kr_progress_logs(审计要求)
- Objective.progress 由所属 KR 的加权平均自动计算
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.okr import (
    KeyResult,
    KRProgressLog,
    KRProgressSource,
    Objective,
    OKRCycle,
    OKRStatus,
)
from app.models.project import Project
from app.models.sprint import Sprint
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/okr", tags=["OKR"])

_writers = require_role(UserRole.admin, UserRole.manager)


# ════════════════════════════════════════════════════════════════
# Schemas
# ════════════════════════════════════════════════════════════════


class CycleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    cycle_type: str = "quarterly"
    start_date: str
    end_date: str


class CycleUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CycleOut(BaseModel):
    id: str
    name: str
    cycle_type: str
    start_date: str
    end_date: str
    status: str


class ObjectiveCreate(BaseModel):
    cycle_id: str
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    project_id: Optional[str] = None
    owner_id: Optional[str] = None
    weight: float = 1.0


class ObjectiveUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    weight: Optional[float] = None
    status: Optional[str] = None


class ObjectiveOut(BaseModel):
    id: str
    cycle_id: str
    title: str
    description: Optional[str]
    owner_id: str
    owner_name: Optional[str] = None
    weight: float
    progress: float
    status: str


class KRCreate(BaseModel):
    objective_id: str
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    sprint_id: Optional[str] = None
    metric_type: str = "percentage"
    target_value: float = 100.0
    unit: Optional[str] = None


class KRUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    confidence: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = Field(default=None, description="本次更新备注,落入进度日志")


class KROut(BaseModel):
    id: str
    objective_id: str
    title: str
    description: Optional[str]
    metric_type: str
    unit: Optional[str]
    target_value: float
    current_value: float
    progress: float
    confidence: float


class TreeKR(BaseModel):
    kr: KROut


class TreeObjective(BaseModel):
    objective: ObjectiveOut
    key_results: list[KROut]


class TreeOut(BaseModel):
    cycle: CycleOut
    objectives: list[TreeObjective]
    summary: dict


class ProgressLogOut(BaseModel):
    id: str
    kr_id: str
    report_id: Optional[str]
    previous_value: float
    new_value: float
    source: str
    confidence: Optional[float]
    note: Optional[str]
    created_at: Optional[str]


# ════════════════════════════════════════════════════════════════
# 内部工具:写进度日志 + 联动更新 Objective.progress
# ════════════════════════════════════════════════════════════════


async def _log_kr_progress(
    db: AsyncSession,
    *,
    kr: KeyResult,
    previous_value: float,
    new_value: float,
    source: KRProgressSource = KRProgressSource.manual,
    confidence: Optional[float] = None,
    note: Optional[str] = None,
    report_id: Optional[uuid.UUID] = None,
    actor_id: Optional[uuid.UUID] = None,
) -> KRProgressLog:
    """记录一次 KR 进度变更"""
    log = KRProgressLog(
        kr_id=kr.id,
        report_id=report_id,
        previous_value=previous_value,
        new_value=new_value,
        source=source,
        confidence=confidence,
        note=note,
        created_by=actor_id,
        tenant_id=kr.tenant_id,
    )
    db.add(log)
    return log


async def _recalc_objective_progress(db: AsyncSession, objective_id: uuid.UUID, tenant_id: str) -> float:
    """根据 KR 进度的加权平均(暂等权)重算 Objective.progress"""
    krs = (
        await db.execute(select(KeyResult).where(KeyResult.objective_id == objective_id, KeyResult.tenant_id == tenant_id))
    ).scalars().all()
    obj = (
        await db.execute(select(Objective).where(Objective.id == objective_id, Objective.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if not obj:
        return 0.0
    if not krs:
        obj.progress = 0.0
    else:
        obj.progress = round(sum(k.progress for k in krs) / len(krs), 1)
    return obj.progress


# ════════════════════════════════════════════════════════════════
# Cycle CRUD
# ════════════════════════════════════════════════════════════════


@router.get("/cycles", response_model=list[CycleOut])
async def list_cycles(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await db.execute(select(OKRCycle).where(OKRCycle.tenant_id == _user.tenant_id).order_by(desc(OKRCycle.start_date)))
    cycles = result.scalars().all()
    return [
        CycleOut(
            id=str(c.id),
            name=c.name,
            cycle_type=c.cycle_type.value,
            start_date=str(c.start_date),
            end_date=str(c.end_date),
            status=c.status.value,
        )
        for c in cycles
    ]


@router.post("/cycles", response_model=CycleOut)
async def create_cycle(
    req: CycleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    cycle = OKRCycle(
        name=req.name,
        cycle_type=req.cycle_type,
        start_date=date_type.fromisoformat(req.start_date),
        end_date=date_type.fromisoformat(req.end_date),
        status=OKRStatus.active,
        created_by=user.id,
        tenant_id=user.tenant_id,
    )
    db.add(cycle)
    await db.commit()
    await db.refresh(cycle)
    return CycleOut(
        id=str(cycle.id),
        name=cycle.name,
        cycle_type=cycle.cycle_type.value,
        start_date=str(cycle.start_date),
        end_date=str(cycle.end_date),
        status=cycle.status.value,
    )


@router.patch("/cycles/{cycle_id}", response_model=CycleOut)
async def update_cycle(
    cycle_id: str,
    req: CycleUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.admin)),
):
    cycle = (
        await db.execute(select(OKRCycle).where(OKRCycle.id == uuid.UUID(cycle_id), OKRCycle.tenant_id == _user.tenant_id))
    ).scalar_one_or_none()
    if not cycle:
        raise HTTPException(404, "Cycle 不存在")
    if req.name:
        cycle.name = req.name
    if req.status:
        cycle.status = OKRStatus(req.status)
    if req.start_date:
        cycle.start_date = date_type.fromisoformat(req.start_date)
    if req.end_date:
        cycle.end_date = date_type.fromisoformat(req.end_date)
    await db.commit()
    await db.refresh(cycle)
    return CycleOut(
        id=str(cycle.id),
        name=cycle.name,
        cycle_type=cycle.cycle_type.value,
        start_date=str(cycle.start_date),
        end_date=str(cycle.end_date),
        status=cycle.status.value,
    )


@router.delete("/cycles/{cycle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cycle(
    cycle_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.admin)),
):
    cycle = (
        await db.execute(select(OKRCycle).where(OKRCycle.id == uuid.UUID(cycle_id), OKRCycle.tenant_id == _user.tenant_id))
    ).scalar_one_or_none()
    if not cycle:
        raise HTTPException(404, "Cycle 不存在")
    await db.delete(cycle)
    await db.commit()


# ════════════════════════════════════════════════════════════════
# Objective CRUD
# ════════════════════════════════════════════════════════════════


@router.get("/objectives", response_model=list[ObjectiveOut])
async def list_objectives(
    cycle_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = (
        select(Objective, User.name)
        .join(User, and_(Objective.owner_id == User.id, User.tenant_id == _user.tenant_id), isouter=True)
        .where(Objective.tenant_id == _user.tenant_id)
    )
    if cycle_id:
        stmt = stmt.where(Objective.cycle_id == uuid.UUID(cycle_id))
    stmt = stmt.order_by(desc(Objective.weight))
    rows = (await db.execute(stmt)).all()
    return [
        ObjectiveOut(
            id=str(o.id),
            cycle_id=str(o.cycle_id),
            title=o.title,
            description=o.description,
            owner_id=str(o.owner_id),
            owner_name=owner_name,
            weight=o.weight,
            progress=o.progress,
            status=o.status.value,
        )
        for o, owner_name in rows
    ]


@router.post("/objectives", response_model=ObjectiveOut)
async def create_objective(
    req: ObjectiveCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_writers),
):
    owner_id = uuid.UUID(req.owner_id) if req.owner_id else user.id
    cycle = (
        await db.execute(select(OKRCycle.id).where(OKRCycle.id == uuid.UUID(req.cycle_id), OKRCycle.tenant_id == user.tenant_id))
    ).scalar_one_or_none()
    if not cycle:
        raise HTTPException(404, "Cycle 不存在")
    owner = (
        await db.execute(select(User.id).where(User.id == owner_id, User.tenant_id == user.tenant_id, User.is_active.is_(True)))
    ).scalar_one_or_none()
    if not owner:
        raise HTTPException(404, "负责人不存在")
    project_uuid = uuid.UUID(req.project_id) if req.project_id else None
    if project_uuid:
        project = (
            await db.execute(
                select(Project.id).where(Project.id == project_uuid, Project.tenant_id == user.tenant_id, Project.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not project:
            raise HTTPException(404, "项目不存在")

    obj = Objective(
        cycle_id=uuid.UUID(req.cycle_id),
        owner_id=owner_id,
        title=req.title,
        description=req.description,
        project_id=project_uuid,
        weight=req.weight,
        created_by=user.id,
        tenant_id=user.tenant_id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return ObjectiveOut(
        id=str(obj.id),
        cycle_id=str(obj.cycle_id),
        title=obj.title,
        description=obj.description,
        owner_id=str(obj.owner_id),
        weight=obj.weight,
        progress=obj.progress,
        status=obj.status.value,
    )


@router.patch("/objectives/{objective_id}", response_model=ObjectiveOut)
async def update_objective(
    objective_id: str,
    req: ObjectiveUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_writers),
):
    obj = (
        await db.execute(select(Objective).where(Objective.id == uuid.UUID(objective_id), Objective.tenant_id == _user.tenant_id))
    ).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Objective 不存在")
    if req.title:
        obj.title = req.title
    if req.description is not None:
        obj.description = req.description
    if req.weight is not None:
        obj.weight = req.weight
    if req.status:
        obj.status = OKRStatus(req.status)
    await db.commit()
    await db.refresh(obj)
    return ObjectiveOut(
        id=str(obj.id),
        cycle_id=str(obj.cycle_id),
        title=obj.title,
        description=obj.description,
        owner_id=str(obj.owner_id),
        weight=obj.weight,
        progress=obj.progress,
        status=obj.status.value,
    )


@router.delete("/objectives/{objective_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_objective(
    objective_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_writers),
):
    obj = (
        await db.execute(select(Objective).where(Objective.id == uuid.UUID(objective_id), Objective.tenant_id == _user.tenant_id))
    ).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Objective 不存在")
    await db.delete(obj)
    await db.commit()


# ════════════════════════════════════════════════════════════════
# Key Result CRUD
# ════════════════════════════════════════════════════════════════


def _kr_out(kr: KeyResult) -> KROut:
    return KROut(
        id=str(kr.id),
        objective_id=str(kr.objective_id),
        title=kr.title,
        description=kr.description,
        metric_type=kr.metric_type,
        unit=kr.unit,
        target_value=kr.target_value,
        current_value=kr.current_value,
        progress=kr.progress,
        confidence=kr.confidence,
    )


@router.get("/key-results", response_model=list[KROut])
async def list_key_results(
    objective_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(KeyResult).where(KeyResult.tenant_id == _user.tenant_id)
    if objective_id:
        stmt = stmt.where(KeyResult.objective_id == uuid.UUID(objective_id))
    krs = (await db.execute(stmt)).scalars().all()
    return [_kr_out(kr) for kr in krs]


@router.post("/key-results", response_model=KROut)
async def create_key_result(
    req: KRCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_writers),
):
    objective = (
        await db.execute(
            select(Objective.id).where(Objective.id == uuid.UUID(req.objective_id), Objective.tenant_id == user.tenant_id)
        )
    ).scalar_one_or_none()
    if not objective:
        raise HTTPException(404, "Objective 不存在")
    sprint_uuid = uuid.UUID(req.sprint_id) if req.sprint_id else None
    if sprint_uuid:
        sprint = (
            await db.execute(select(Sprint.id).where(Sprint.id == sprint_uuid, Sprint.tenant_id == user.tenant_id))
        ).scalar_one_or_none()
        if not sprint:
            raise HTTPException(404, "Sprint 不存在")

    kr = KeyResult(
        objective_id=uuid.UUID(req.objective_id),
        owner_id=user.id,
        title=req.title,
        description=req.description,
        sprint_id=sprint_uuid,
        metric_type=req.metric_type,
        target_value=req.target_value,
        unit=req.unit,
        created_by=user.id,
        tenant_id=user.tenant_id,
    )
    db.add(kr)
    await db.commit()
    await db.refresh(kr)
    return _kr_out(kr)


@router.patch("/key-results/{kr_id}", response_model=KROut)
async def update_key_result(
    kr_id: str,
    req: KRUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_writers),
):
    kr = (
        await db.execute(select(KeyResult).where(KeyResult.id == uuid.UUID(kr_id), KeyResult.tenant_id == user.tenant_id))
    ).scalar_one_or_none()
    if not kr:
        raise HTTPException(404, "KR 不存在")

    if req.title:
        kr.title = req.title
    if req.description is not None:
        kr.description = req.description
    if req.target_value is not None:
        kr.target_value = req.target_value
    if req.unit is not None:
        kr.unit = req.unit
    if req.confidence is not None:
        kr.confidence = max(0.0, min(1.0, req.confidence))

    # 进度变更走日志
    if req.current_value is not None and req.current_value != kr.current_value:
        prev = kr.current_value
        kr.current_value = req.current_value
        await _log_kr_progress(
            db,
            kr=kr,
            previous_value=prev,
            new_value=req.current_value,
            source=KRProgressSource.manual,
            note=req.note or "手工更新",
            actor_id=user.id,
        )
        await _recalc_objective_progress(db, kr.objective_id, user.tenant_id)

    await db.commit()
    await db.refresh(kr)
    return _kr_out(kr)


@router.delete("/key-results/{kr_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key_result(
    kr_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_writers),
):
    kr = (
        await db.execute(select(KeyResult).where(KeyResult.id == uuid.UUID(kr_id), KeyResult.tenant_id == _user.tenant_id))
    ).scalar_one_or_none()
    if not kr:
        raise HTTPException(404, "KR 不存在")
    objective_id = kr.objective_id
    await db.delete(kr)
    await db.flush()
    await _recalc_objective_progress(db, objective_id, _user.tenant_id)
    await db.commit()


# ════════════════════════════════════════════════════════════════
# 进度日志查询
# ════════════════════════════════════════════════════════════════


@router.get("/key-results/{kr_id}/progress-logs", response_model=list[ProgressLogOut])
async def list_kr_progress_logs(
    kr_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rows = (
        (
            await db.execute(
                select(KRProgressLog)
                .where(KRProgressLog.kr_id == uuid.UUID(kr_id), KRProgressLog.tenant_id == _user.tenant_id)
                .order_by(desc(KRProgressLog.created_at))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        ProgressLogOut(
            id=str(r.id),
            kr_id=str(r.kr_id),
            report_id=str(r.report_id) if r.report_id else None,
            previous_value=r.previous_value,
            new_value=r.new_value,
            source=r.source.value,
            confidence=r.confidence,
            note=r.note,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


# ════════════════════════════════════════════════════════════════
# 树状视图(给前端 OKR 看板用,一个 GET 拿到完整结构)
# ════════════════════════════════════════════════════════════════


@router.get("/tree", response_model=TreeOut)
async def okr_tree(
    cycle_id: Optional[str] = Query(None, description="不传则取最新 active 周期"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """返回某个周期的完整 O/KR 树 + 汇总指标"""
    # 选周期
    if cycle_id:
        cycle = (
            await db.execute(select(OKRCycle).where(OKRCycle.id == uuid.UUID(cycle_id), OKRCycle.tenant_id == _user.tenant_id))
        ).scalar_one_or_none()
    else:
        cycle = (
            await db.execute(
                select(OKRCycle)
                .where(OKRCycle.status == OKRStatus.active, OKRCycle.tenant_id == _user.tenant_id)
                .order_by(desc(OKRCycle.start_date))
                .limit(1)
            )
        ).scalar_one_or_none()
    if not cycle:
        raise HTTPException(404, "未找到 OKR 周期")

    cycle_out = CycleOut(
        id=str(cycle.id),
        name=cycle.name,
        cycle_type=cycle.cycle_type.value,
        start_date=str(cycle.start_date),
        end_date=str(cycle.end_date),
        status=cycle.status.value,
    )

    # 所有 Objectives + 所有 KR(两次查询一次拼装)
    obj_rows = (
        await db.execute(
            select(Objective, User.name)
            .join(User, and_(Objective.owner_id == User.id, User.tenant_id == _user.tenant_id), isouter=True)
            .where(Objective.cycle_id == cycle.id, Objective.tenant_id == _user.tenant_id)
            .order_by(desc(Objective.weight))
        )
    ).all()

    if not obj_rows:
        return TreeOut(
            cycle=cycle_out,
            objectives=[],
            summary={"objective_count": 0, "kr_count": 0, "avg_progress": 0},
        )

    obj_ids = [o.id for o, _ in obj_rows]
    krs = (
        await db.execute(select(KeyResult).where(KeyResult.objective_id.in_(obj_ids), KeyResult.tenant_id == _user.tenant_id))
    ).scalars().all()

    kr_by_obj: dict[uuid.UUID, list[KeyResult]] = {}
    for kr in krs:
        kr_by_obj.setdefault(kr.objective_id, []).append(kr)

    tree_objectives = []
    progress_values = []
    for obj, owner_name in obj_rows:
        tree_objectives.append(
            TreeObjective(
                objective=ObjectiveOut(
                    id=str(obj.id),
                    cycle_id=str(obj.cycle_id),
                    title=obj.title,
                    description=obj.description,
                    owner_id=str(obj.owner_id),
                    owner_name=owner_name,
                    weight=obj.weight,
                    progress=obj.progress,
                    status=obj.status.value,
                ),
                key_results=[_kr_out(kr) for kr in kr_by_obj.get(obj.id, [])],
            )
        )
        progress_values.append(obj.progress)

    avg = round(sum(progress_values) / len(progress_values), 1) if progress_values else 0
    summary = {
        "objective_count": len(tree_objectives),
        "kr_count": len(krs),
        "avg_progress": avg,
        "on_track": sum(1 for p in progress_values if p >= 70),
        "at_risk": sum(1 for p in progress_values if 40 <= p < 70),
        "behind": sum(1 for p in progress_values if p < 40),
    }
    return TreeOut(cycle=cycle_out, objectives=tree_objectives, summary=summary)
