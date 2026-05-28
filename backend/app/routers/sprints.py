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
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import (
    SprintTask,
    TaskPriority,
    TaskStatus,
)
from app.models.user import User, UserRole
from app.schemas.project import SprintComplete, SprintCreate
from app.services.critical_path import compute_critical_path
from app.services.deletion_history import mark_soft_delete_restored, record_soft_delete
from app.services.health_engine import refresh_sprint_health
from app.services.sprint_aggregator import (
    compute_burndown_series,
    compute_velocity_history,
    snapshot_burndown,
)

router = APIRouter(prefix="/api/v1/sprints", tags=["Sprints (Software Track)"])

_mgr = require_role(UserRole.manager, UserRole.admin)


def _member_visible_project_ids(user: User):
    return (
        select(ProjectMember.project_id)
        .where(
            ProjectMember.user_id == user.id,
            ProjectMember.left_at.is_(None),
            ProjectMember.tenant_id == user.tenant_id,
        )
        .scalar_subquery()
    )


async def _get_visible_sprint(db: AsyncSession, sprint_id: uuid.UUID, user: User) -> Sprint:
    conditions = [
        Sprint.id == sprint_id,
        Sprint.tenant_id == user.tenant_id,
        Project.tenant_id == user.tenant_id,
        Project.deleted_at.is_(None),
    ]
    if user.role == UserRole.employee:
        conditions.append(Sprint.project_id.in_(_member_visible_project_ids(user)))
    sprint = (
        await db.execute(select(Sprint).join(Project, Sprint.project_id == Project.id).where(and_(*conditions)))
    ).scalar_one_or_none()
    if sprint is None:
        raise HTTPException(404, "Sprint 不存在")
    return sprint


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
    project = (
        await db.execute(
            select(Project).where(
                Project.id == data.project_id,
                Project.deleted_at.is_(None),
                Project.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "项目不存在")

    if data.stage_id is not None:
        stage = (
            await db.execute(
                select(ProjectStage.id).where(
                    ProjectStage.id == data.stage_id,
                    ProjectStage.project_id == data.project_id,
                    ProjectStage.tenant_id == _user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if stage is None:
            raise HTTPException(400, "Sprint 关联的阶段不属于所选项目")

    duplicate = (
        await db.execute(
            select(Sprint.id).where(
                Sprint.project_id == data.project_id,
                Sprint.sprint_number == data.sprint_number,
                Sprint.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该项目下 Sprint 编号已存在")

    sprint = Sprint(
        project_id=data.project_id,
        stage_id=data.stage_id,
        sprint_number=data.sprint_number,
        goal=data.goal,
        start_date=data.start_date,
        end_date=data.end_date,
        planned_story_points=data.planned_story_points,
        tenant_id=_user.tenant_id,
        created_by=_user.id,
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
    project = (
        await db.execute(
            select(Project.id).where(
                Project.id == project_id,
                Project.deleted_at.is_(None),
                Project.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "项目不存在")
    result = await db.execute(
        select(Sprint)
        .where(Sprint.project_id == project_id, Sprint.tenant_id == _user.tenant_id)
        .order_by(Sprint.sprint_number)
    )
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
    sprint = await _get_visible_sprint(db, sprint_id, _user)
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
    sprint = await _get_visible_sprint(db, sprint_id, _user)

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
    current_user: User = Depends(get_current_user),
):
    await _get_visible_sprint(db, sprint_id, current_user)
    # V2.5 Stage 2:默认过滤已软删
    rows = (
        (
            await db.execute(
                select(SprintTask).where(
                    and_(
                        SprintTask.sprint_id == sprint_id,
                        SprintTask.deleted_at.is_(None),
                        SprintTask.tenant_id == current_user.tenant_id,
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
    await _get_visible_sprint(db, sprint_id, user)

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
        tenant_id=user.tenant_id,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _task_out(t)


# ════════════════════════════════════════════════════════════════
# V2.5 Stage 2:Sprint 任务批量软删 / 恢复 / 已删列表
# 静态 /tasks/batch 路由必须放在 /tasks/{task_id} 动态路由之前。
# ════════════════════════════════════════════════════════════════


class BatchTaskBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200, description="任务 ID 列表")


@router.delete("/tasks/batch")
async def batch_soft_delete_tasks(
    body: BatchTaskBody = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_mgr),
):
    """
    批量软删 Sprint 任务(SET deleted_at = now())。
    """
    cond = and_(
        SprintTask.id.in_(body.ids),
        SprintTask.deleted_at.is_(None),
        SprintTask.tenant_id == user.tenant_id,
    )

    pre_rows = (await db.execute(select(SprintTask.id, SprintTask.sprint_id).where(cond))).all()
    sprint_ids = {r.sprint_id for r in pre_rows}

    deleted_at = datetime.now(timezone.utc)
    result = await db.execute(update(SprintTask).where(cond).values(deleted_at=deleted_at).returning(SprintTask.id))
    deleted_ids = [r[0] for r in result.all()]
    await record_soft_delete(
        db,
        actor_id=user.id,
        table_name="sprint_tasks",
        record_ids=deleted_ids,
        deleted_at=deleted_at,
        tenant_id=user.tenant_id,
    )
    await db.commit()

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
    user: User = Depends(_mgr),
):
    """
    批量恢复已软删任务(SET deleted_at = NULL)。
    """
    cond = and_(
        SprintTask.id.in_(body.ids),
        SprintTask.deleted_at.is_not(None),
        SprintTask.tenant_id == user.tenant_id,
    )

    pre_rows = (await db.execute(select(SprintTask.id, SprintTask.sprint_id).where(cond))).all()
    sprint_ids = {r.sprint_id for r in pre_rows}

    result = await db.execute(update(SprintTask).where(cond).values(deleted_at=None).returning(SprintTask.id))
    restored_ids = [r[0] for r in result.all()]
    await mark_soft_delete_restored(
        db,
        table_name="sprint_tasks",
        record_ids=restored_ids,
        restored_by=user.id,
        tenant_id=user.tenant_id,
    )
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
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(403, "仅 admin 可访问回收站")

    rows = (
        await db.execute(
            select(SprintTask, Sprint.sprint_number, Sprint.project_id)
            .join(Sprint, SprintTask.sprint_id == Sprint.id)
            .where(
                SprintTask.deleted_at.is_not(None),
                SprintTask.tenant_id == current_user.tenant_id,
                Sprint.tenant_id == current_user.tenant_id,
            )
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


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr),
):
    t = await db.get(SprintTask, task_id)
    if not t or t.tenant_id != _user.tenant_id:
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
    user: User = Depends(_mgr),
):
    """V2.5 Stage 2:单条软删(SET deleted_at=now())。已删的再调返回 404 避免覆盖时间戳。"""
    t = await db.get(SprintTask, task_id)
    if not t or t.tenant_id != user.tenant_id or t.deleted_at is not None:
        raise HTTPException(404, "task 不存在")
    sid = t.sprint_id
    deleted_at = datetime.now(timezone.utc)
    t.deleted_at = deleted_at
    await record_soft_delete(
        db,
        actor_id=user.id,
        table_name="sprint_tasks",
        record_ids=[t.id],
        deleted_at=deleted_at,
        tenant_id=user.tenant_id,
    )
    await db.commit()
    # 删除后重算燃尽快照(任务不再计入剩余点数)
    await snapshot_burndown(db, sid)
    await db.commit()


@router.get("/{sprint_id}/burndown")
async def get_burndown(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """燃尽图序列(理想 + 实际 + 预测)"""
    await _get_visible_sprint(db, sprint_id, current_user)
    data = await compute_burndown_series(db, sprint_id, tenant_id=current_user.tenant_id)
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
    await _get_visible_sprint(db, sprint_id, _user)
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
    current_user: User = Depends(get_current_user),
):
    """计算 Sprint 关键路径。persist=true 时把结果回写到 task.is_on_critical_path"""
    await _get_visible_sprint(db, sprint_id, current_user)
    if persist and current_user.role not in (UserRole.manager, UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="持久化关键路径需要管理权限")
    result = await compute_critical_path(db, sprint_id, persist=persist)
    if persist:
        await db.commit()
    return result


@router.get("/project/{project_id}/velocity")
async def project_velocity(
    project_id: uuid.UUID,
    last_n: int = 6,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """项目历史 Sprint 速率(用于交付预测)"""
    project_conditions = [
        Project.id == project_id,
        Project.deleted_at.is_(None),
        Project.tenant_id == current_user.tenant_id,
    ]
    if current_user.role == UserRole.employee:
        project_conditions.append(Project.id.in_(_member_visible_project_ids(current_user)))
    project = (await db.execute(select(Project.id).where(and_(*project_conditions)))).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "项目不存在")
    return await compute_velocity_history(db, project_id, last_n=last_n, tenant_id=current_user.tenant_id)
