"""
app/routers/sprints.py — 软件轨 Sprint 敏捷管理 API

核心端点：
  POST   /api/v1/sprints/                  创建 Sprint（默认14天）
  GET    /api/v1/sprints/project/{id}      某项目所有 Sprint 列表
  GET    /api/v1/sprints/{id}              Sprint 详情（含健康度曲线）
  PATCH  /api/v1/sprints/{id}/start        开始 Sprint
  PATCH  /api/v1/sprints/{id}/complete     完成 Sprint（填写回顾三问）

Sprint 健康度来源：该 Sprint 期间所有软件轨成员的日报 ai_score 均值。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import (
    SprintTask,
    TaskPriority,
    TaskStatus,
)
from app.models.user import User, UserRole
from app.schemas.project import SprintComplete, SprintCreate
from app.services.critical_path import compute_critical_path
from app.services.health_engine import refresh_sprint_health
from app.services.sprint_aggregator import (
    compute_burndown_series,
    compute_velocity_history,
    snapshot_burndown,
)

router = APIRouter(prefix="/api/v1/sprints", tags=["Sprints (Software Track)"])

_mgr = require_role(UserRole.manager, UserRole.admin)


@router.post("/")
async def create_sprint(
    data: SprintCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """
    创建 Sprint。
    如果未指定 end_date 系统自动 start_date + 13 天（14天周期）。
    """
    sprint = Sprint(
        project_id=data.project_id,
        stage_id=data.stage_id,
        sprint_number=data.sprint_number,
        goal=data.goal,
        start_date=data.start_date,
        end_date=data.end_date,
        planned_story_points=data.planned_story_points,
    )
    db.add(sprint)
    await db.commit()
    return {
        "message": f"Sprint #{data.sprint_number} 已创建",
        "sprint_id": str(sprint.id),
        "start_date": data.start_date,
        "end_date": data.end_date,
        "duration_days": (data.end_date - data.start_date).days + 1,
    }


@router.get("/project/{project_id}")
async def list_sprints(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """查看项目所有 Sprint 列表（速度趋势数据）"""
    result = await db.execute(select(Sprint).where(Sprint.project_id == project_id).order_by(Sprint.sprint_number))
    sprints = result.scalars().all()

    return [
        {
            "sprint_id": str(s.id),
            "sprint_number": s.sprint_number,
            "goal": s.goal,
            "start_date": s.start_date,
            "end_date": s.end_date,
            "status": s.status,
            "health_score": s.health_score,
            "planned_sp": s.planned_story_points,
            "completed_sp": s.completed_story_points,
            "velocity_pct": (
                round(s.completed_story_points / s.planned_story_points * 100) if s.planned_story_points else None
            ),
            "retrospective": s.retrospective,
        }
        for s in sprints
    ]


@router.patch("/{sprint_id}/start")
async def start_sprint(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """将 Sprint 状态从 planning → active"""
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()
    if not sprint:
        raise HTTPException(404, "Sprint 不存在")
    if sprint.status != SprintStatus.planning:
        raise HTTPException(400, f"Sprint 当前状态为 {sprint.status}，无法启动")

    sprint.status = SprintStatus.active
    await db.commit()
    return {"message": f"Sprint #{sprint.sprint_number} 已启动", "status": "active"}


@router.patch("/{sprint_id}/complete")
async def complete_sprint(
    sprint_id: uuid.UUID,
    data: SprintComplete,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """
    完成 Sprint：
    - 填写 Story Points 完成量（velocity）
    - 填写回顾三问（went_well / improve / action_items）
    - 自动聚合计算该 Sprint 的健康度
    """
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()
    if not sprint:
        raise HTTPException(404, "Sprint 不存在")

    sprint.completed_story_points = data.completed_story_points
    sprint.retrospective = data.retrospective
    sprint.status = SprintStatus.completed
    # 最后一次快照,锁定燃尽终态
    await snapshot_burndown(db, sprint_id)
    await db.commit()

    # 聚合健康度
    await refresh_sprint_health(db, sprint_id)

    return {
        "message": f"Sprint #{sprint.sprint_number} 已完成",
        "velocity": data.completed_story_points,
        "health_score": sprint.health_score,
        "completion_rate": (
            f"{round(data.completed_story_points / sprint.planned_story_points * 100)}%"
            if sprint.planned_story_points
            else "N/A"
        ),
    }


# ════════════════════════════════════════════════════════════════
# Week 7:Tasks / Burndown / Critical Path
# ════════════════════════════════════════════════════════════════


class TaskCreate(BaseModel):
    sprint_id: str
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    kr_id: Optional[str] = None
    assignee_id: Optional[str] = None
    story_points: int = 1
    priority: str = "p2"
    depends_on: Optional[list[str]] = None
    planned_start: Optional[str] = None  # ISO date
    planned_end: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    story_points: Optional[int] = None
    actual_story_points: Optional[int] = None
    assignee_id: Optional[str] = None
    depends_on: Optional[list[str]] = None
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None


class TaskOut(BaseModel):
    id: str
    sprint_id: str
    title: str
    description: Optional[str]
    kr_id: Optional[str]
    assignee_id: Optional[str]
    story_points: int
    actual_story_points: Optional[int]
    status: str
    priority: str
    is_on_critical_path: bool
    depends_on: list[str]
    planned_start: Optional[str]
    planned_end: Optional[str]
    actual_start: Optional[str]
    actual_end: Optional[str]


def _task_out(t: SprintTask) -> TaskOut:
    return TaskOut(
        id=str(t.id),
        sprint_id=str(t.sprint_id),
        title=t.title,
        description=t.description,
        kr_id=str(t.kr_id) if t.kr_id else None,
        assignee_id=str(t.assignee_id) if t.assignee_id else None,
        story_points=t.story_points,
        actual_story_points=t.actual_story_points,
        status=t.status.value,
        priority=t.priority.value,
        is_on_critical_path=t.is_on_critical_path,
        depends_on=list(t.depends_on or []),
        planned_start=t.planned_start.isoformat() if t.planned_start else None,
        planned_end=t.planned_end.isoformat() if t.planned_end else None,
        actual_start=t.actual_start.isoformat() if t.actual_start else None,
        actual_end=t.actual_end.isoformat() if t.actual_end else None,
    )


def _parse_date(s: Optional[str]):
    if not s:
        return None
    from datetime import date as _date

    return _date.fromisoformat(s)


@router.get("/{sprint_id}/tasks", response_model=list[TaskOut])
async def list_tasks(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    # V2.5 Stage 2:默认过滤已软删
    rows = (
        (
            await db.execute(
                select(SprintTask).where(
                    and_(
                        SprintTask.sprint_id == sprint_id,
                        SprintTask.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    return [_task_out(t) for t in rows]


@router.post("/{sprint_id}/tasks", response_model=TaskOut)
async def create_task(
    sprint_id: uuid.UUID,
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_mgr),
):
    if str(sprint_id) != payload.sprint_id:
        raise HTTPException(400, "sprint_id 不一致")
    sprint = await db.get(Sprint, sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint 不存在")

    t = SprintTask(
        sprint_id=sprint_id,
        kr_id=uuid.UUID(payload.kr_id) if payload.kr_id else None,
        assignee_id=uuid.UUID(payload.assignee_id) if payload.assignee_id else None,
        title=payload.title,
        description=payload.description,
        story_points=max(payload.story_points, 0),
        priority=TaskPriority(payload.priority),
        depends_on=payload.depends_on or [],
        planned_start=_parse_date(payload.planned_start),
        planned_end=_parse_date(payload.planned_end),
        created_by=user.id,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _task_out(t)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr),
):
    t = await db.get(SprintTask, task_id)
    if not t:
        raise HTTPException(404, "task 不存在")

    if payload.title is not None:
        t.title = payload.title
    if payload.description is not None:
        t.description = payload.description
    if payload.status is not None:
        new_status = TaskStatus(payload.status)
        # done 时若没填 actual_end,自动补今天
        from datetime import date as _date

        if new_status == TaskStatus.done and not t.actual_end:
            t.actual_end = _date.today()
        if new_status == TaskStatus.in_progress and not t.actual_start:
            t.actual_start = _date.today()
        t.status = new_status
    if payload.priority is not None:
        t.priority = TaskPriority(payload.priority)
    if payload.story_points is not None:
        t.story_points = max(payload.story_points, 0)
    if payload.actual_story_points is not None:
        t.actual_story_points = max(payload.actual_story_points, 0)
    if payload.assignee_id is not None:
        t.assignee_id = uuid.UUID(payload.assignee_id) if payload.assignee_id else None
    if payload.depends_on is not None:
        t.depends_on = payload.depends_on
    if payload.planned_start is not None:
        t.planned_start = _parse_date(payload.planned_start)
    if payload.planned_end is not None:
        t.planned_end = _parse_date(payload.planned_end)
    if payload.actual_start is not None:
        t.actual_start = _parse_date(payload.actual_start)
    if payload.actual_end is not None:
        t.actual_end = _parse_date(payload.actual_end)

    await db.commit()
    await db.refresh(t)

    # 状态变更后立刻刷新当日燃尽快照
    await snapshot_burndown(db, t.sprint_id)
    await db.commit()
    return _task_out(t)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr),
):
    """V2.5 Stage 2:单条软删(SET deleted_at=now())。已删的再调返回 404 避免覆盖时间戳。"""
    t = await db.get(SprintTask, task_id)
    if not t or t.deleted_at is not None:
        raise HTTPException(404, "task 不存在")
    sid = t.sprint_id
    t.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    # 删除后重算燃尽快照(任务不再计入剩余点数)
    await snapshot_burndown(db, sid)
    await db.commit()


# ════════════════════════════════════════════════════════════════
# V2.5 Stage 2:Sprint 任务批量软删 / 恢复 / 已删列表
# ════════════════════════════════════════════════════════════════


class BatchTaskBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200, description="任务 ID 列表")


@router.delete("/tasks/batch")
async def batch_soft_delete_tasks(
    body: BatchTaskBody = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr),
):
    """
    批量软删 Sprint 任务(SET deleted_at = now())。

    - manager / admin 可调用
    - 已被软删过的不会重复 deleted_at
    - 删完后对受影响的 sprint 各重算一次燃尽快照
    """
    cond = and_(SprintTask.id.in_(body.ids), SprintTask.deleted_at.is_(None))

    # 先查受影响的 sprint_id 集合(用于回填快照)
    pre_rows = (await db.execute(select(SprintTask.id, SprintTask.sprint_id).where(cond))).all()
    sprint_ids = {r.sprint_id for r in pre_rows}

    result = await db.execute(
        update(SprintTask).where(cond).values(deleted_at=datetime.now(timezone.utc)).returning(SprintTask.id)
    )
    deleted_ids = [r[0] for r in result.all()]
    await db.commit()

    # 为每个受影响 sprint 重算一次燃尽
    for sid in sprint_ids:
        await snapshot_burndown(db, sid)
    if sprint_ids:
        await db.commit()

    return {
        "requested": len(body.ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": [str(i) for i in deleted_ids],
    }


@router.patch("/tasks/batch-restore")
async def batch_restore_tasks(
    body: BatchTaskBody = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr),
):
    """
    批量恢复已软删任务(SET deleted_at = NULL)。

    - 已 deleted_at IS NULL 的不会被重复恢复
    - 恢复后对受影响 sprint 重算燃尽快照
    """
    cond = and_(SprintTask.id.in_(body.ids), SprintTask.deleted_at.is_not(None))

    pre_rows = (await db.execute(select(SprintTask.id, SprintTask.sprint_id).where(cond))).all()
    sprint_ids = {r.sprint_id for r in pre_rows}

    result = await db.execute(update(SprintTask).where(cond).values(deleted_at=None).returning(SprintTask.id))
    restored_ids = [r[0] for r in result.all()]
    await db.commit()

    for sid in sprint_ids:
        await snapshot_burndown(db, sid)
    if sprint_ids:
        await db.commit()

    return {
        "requested": len(body.ids),
        "restored_count": len(restored_ids),
        "restored_ids": [str(i) for i in restored_ids],
    }


@router.get("/tasks/deleted")
async def list_deleted_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    回收站:已软删的 Sprint 任务列表(admin only)。

    返回包含 sprint_number 与 project 名,便于回收站展示「哪个 Sprint 的任务」。
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(403, "仅 admin 可访问回收站")

    rows = (
        await db.execute(
            select(SprintTask, Sprint.sprint_number, Sprint.project_id)
            .join(Sprint, SprintTask.sprint_id == Sprint.id)
            .where(SprintTask.deleted_at.is_not(None))
            .order_by(SprintTask.deleted_at.desc())
        )
    ).all()

    items = [
        {
            "id": str(t.SprintTask.id),
            "title": t.SprintTask.title,
            "story_points": t.SprintTask.story_points,
            "status": t.SprintTask.status.value,
            "priority": t.SprintTask.priority.value,
            "sprint_id": str(t.SprintTask.sprint_id),
            "sprint_number": t.sprint_number,
            "project_id": str(t.project_id),
            "deleted_at": t.SprintTask.deleted_at.isoformat() if t.SprintTask.deleted_at else None,
        }
        for t in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/{sprint_id}/burndown")
async def get_burndown(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """燃尽图序列(理想 + 实际 + 预测)"""
    data = await compute_burndown_series(db, sprint_id)
    if "error" in data:
        raise HTTPException(404, data["error"])
    return data


@router.post("/{sprint_id}/snapshot", response_model=dict)
async def manual_snapshot(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr),
):
    """手工触发一次燃尽快照(测试 / 异常补点用)"""
    snap = await snapshot_burndown(db, sprint_id)
    await db.commit()
    return {
        "snapshot_date": snap.snapshot_date.isoformat(),
        "remaining_points": snap.remaining_points,
        "total_points": snap.total_points,
        "done_count": snap.done_count,
        "blocked_count": snap.blocked_count,
    }


@router.get("/{sprint_id}/critical-path")
async def get_critical_path(
    sprint_id: uuid.UUID,
    persist: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """计算 Sprint 关键路径。persist=true 时把结果回写到 task.is_on_critical_path"""
    result = await compute_critical_path(db, sprint_id, persist=persist)
    if persist:
        await db.commit()
    return result


@router.get("/project/{project_id}/velocity")
async def project_velocity(
    project_id: uuid.UUID,
    last_n: int = 6,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """项目历史 Sprint 速率(用于交付预测)"""
    return await compute_velocity_history(db, project_id, last_n=last_n)
