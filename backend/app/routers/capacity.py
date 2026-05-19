"""
app/routers/capacity.py — 资源负载水位 API

端点:
- GET  /capacity/sprint/{sprint_id}             单 Sprint 全员水位
- POST /capacity/sprint/{sprint_id}/snapshot    手工刷新该 Sprint 水位
- GET  /capacity/sprint/{sprint_id}/rebalance   AI 调配建议
- GET  /capacity/overloaded                     当前过载人员(全局)
- GET  /capacity/underutilized                  当前闲置人员
- GET  /capacity/department-summary             部门级聚合
- GET  /capacity/users/{user_id}/timeline       某用户跨 Sprint 水位时间线
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.capacity import CapacitySnapshot
from app.models.sprint import Sprint
from app.models.user import User, UserRole
from app.services.capacity_engine import (
    _snapshot_to_dict,
    compute_user_capacity,
    department_capacity_summary,
    find_overloaded,
    find_underutilized,
    snapshot_sprint_capacity,
    suggest_rebalance,
)

router = APIRouter(prefix="/api/v1/capacity", tags=["资源水位"])

_writers = require_role(UserRole.admin, UserRole.manager)


# ────────────────────────────────────────────────────────────────
# 单 Sprint 视图
# ────────────────────────────────────────────────────────────────


@router.get("/sprint/{sprint_id}")
async def sprint_capacity(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """单 Sprint 全员水位(实时计算,不依赖快照)"""
    sprint = await db.get(Sprint, sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint 不存在")

    from sqlalchemy import and_
    from app.models.sprint_task import SprintTask

    user_ids = [
        r[0] for r in (
            await db.execute(
                select(SprintTask.assignee_id)
                .where(
                    and_(
                        SprintTask.sprint_id == sprint_id,
                        SprintTask.assignee_id.is_not(None),
                    )
                )
                .distinct()
            )
        ).all()
    ]
    if not user_ids:
        return {"sprint_id": str(sprint_id), "count": 0, "members": []}

    users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
    members = []
    for u in users:
        m = await compute_user_capacity(db, u, sprint)
        members.append(m)
    members.sort(key=lambda x: x["utilization"], reverse=True)

    return {
        "sprint_id": str(sprint_id),
        "sprint_number": sprint.sprint_number,
        "sprint_goal": sprint.goal,
        "count": len(members),
        "members": members,
        "summary": {
            "overload": sum(1 for m in members if m["level"] == "overload"),
            "high": sum(1 for m in members if m["level"] == "high"),
            "healthy": sum(1 for m in members if m["level"] == "healthy"),
            "idle": sum(1 for m in members if m["level"] == "idle"),
        },
    }


@router.post("/sprint/{sprint_id}/snapshot")
async def manual_snapshot(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_writers),
):
    """手工刷新该 Sprint 全员水位快照(写入 capacity_snapshots)"""
    rows = await snapshot_sprint_capacity(db, sprint_id)
    await db.commit()
    return {"snapshot_count": len(rows)}


@router.get("/sprint/{sprint_id}/rebalance")
async def rebalance(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """AI 任务调配建议(从过载 → 闲置)"""
    return await suggest_rebalance(db, sprint_id)


# ────────────────────────────────────────────────────────────────
# 全局视图
# ────────────────────────────────────────────────────────────────


@router.get("/overloaded")
async def list_overloaded(
    sprint_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return {"items": await find_overloaded(db, sprint_id=sprint_id, limit=limit)}


@router.get("/underutilized")
async def list_underutilized(
    sprint_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return {"items": await find_underutilized(db, sprint_id=sprint_id, limit=limit)}


@router.get("/department-summary")
async def department_summary(
    sprint_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await department_capacity_summary(db, sprint_id=sprint_id)


@router.get("/users/{user_id}/timeline")
async def user_capacity_timeline(
    user_id: uuid.UUID,
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """某用户跨 Sprint 的水位时间线(用于看个人负载演变)"""
    rows = (
        await db.execute(
            select(CapacitySnapshot, Sprint)
            .join(Sprint, CapacitySnapshot.sprint_id == Sprint.id)
            .where(CapacitySnapshot.user_id == user_id)
            .order_by(desc(Sprint.start_date))
            .limit(limit)
        )
    ).all()

    items = []
    for snap, sprint in reversed(rows):
        items.append(
            {
                "sprint_id": str(sprint.id),
                "sprint_number": sprint.sprint_number,
                "start_date": sprint.start_date.isoformat(),
                "end_date": sprint.end_date.isoformat(),
                "utilization": snap.utilization,
                "level": snap.level.value,
                "allocated_points": snap.allocated_points,
                "completed_points": snap.completed_points,
                "effective_capacity": snap.effective_capacity,
            }
        )

    user = await db.get(User, user_id)
    return {
        "user": {"id": str(user_id), "name": user.name if user else "?",
                  "department": user.department if user else None},
        "count": len(items),
        "timeline": items,
    }
