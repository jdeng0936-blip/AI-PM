"""
app/routers/projects.py — 项目生命周期管理 API

核心端点：
  POST   /api/v1/projects/           立项（自动初始化5个 IPD 阶段）
  GET    /api/v1/projects/           项目列表
  GET    /api/v1/projects/overview   宏观总览（红绿黄健康矩阵）
  GET    /api/v1/projects/{id}       项目详情（含全部阶段）
  GET    /api/v1/projects/{id}/gantt 甘特图数据
  PATCH  /api/v1/stages/{id}         更新阶段进度/里程碑
  POST   /api/v1/projects/{id}/members 添加项目成员
"""
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.project import Project, ProjectStatus
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage, STAGE_DEFINITIONS
from app.models.user import UserRole
from app.schemas.project import (
    GanttStage,
    ProjectCreate,
    ProjectMemberAdd,
    ProjectOverviewItem,
    StageUpdate,
)
from app.services.health_engine import refresh_project_health

router = APIRouter(prefix="/api/v1/projects", tags=["Projects (IPD)"])
stages_router = APIRouter(prefix="/api/v1/stages", tags=["Stages"])

_mgr = require_role(UserRole.manager, UserRole.admin)


# ── 立项（自动初始化5个 IPD 阶段）────────────────────────────────
@router.post("/")
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    creator=Depends(_mgr),
):
    """
    立项并自动展开5个 IPD 阶段节点。
    每个阶段的计划时间从 planned_launch_date 倒推分配。
    """
    # 防重复编号
    existing = await db.execute(select(Project).where(Project.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"项目编号 {data.code} 已存在")

    project = Project(
        name=data.name,
        code=data.code,
        description=data.description,
        track=data.track,
        planned_launch_date=data.planned_launch_date,
        budget_total=data.budget_total,
        budget_alert_threshold=data.budget_alert_threshold,
        created_by=creator.id,
    )
    db.add(project)
    await db.flush()  # 获取 project.id

    # 自动初始化5个阶段（按典型工期倒推日期）
    total_days = sum(d for _, _, _, d in STAGE_DEFINITIONS)
    stage_start = (
        data.planned_launch_date - timedelta(days=total_days)
        if data.planned_launch_date
        else date.today()
    )

    for num, name, track_str, duration in STAGE_DEFINITIONS:
        stage_end = stage_start + timedelta(days=duration - 1)
        stage = ProjectStage(
            project_id=project.id,
            stage_number=num,
            stage_name=name,
            track=track_str,
            planned_start=stage_start,
            planned_end=stage_end,
            health_status="green" if num == 1 else "locked",  # 仅第1阶段解锁
        )
        db.add(stage)
        stage_start = stage_end + timedelta(days=1)

    await db.commit()
    return {
        "message": "项目创建成功，已自动初始化5个 IPD 阶段",
        "project_id": str(project.id),
        "code": project.code,
    }


# ── 项目总览（红绿黄健康矩阵）────────────────────────────────────
@router.get("/overview")
async def projects_overview(
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """
    管理层宏观视图：所有活跃项目的健康矩阵。
    red / yellow / green 一目了然，替代零散的周会汇报。
    """
    result = await db.execute(
        select(Project).where(Project.status == ProjectStatus.active)
        .order_by(Project.health_score.asc())  # 最差的排最前
    )
    projects = result.scalars().all()

    items = []
    for p in projects:
        # 拉取当前阶段信息
        stage_result = await db.execute(
            select(ProjectStage).where(
                and_(
                    ProjectStage.project_id == p.id,
                    ProjectStage.stage_number == p.current_stage,
                )
            )
        )
        stage = stage_result.scalar_one_or_none()

        today = date.today()
        days_to_deadline = (
            (p.planned_launch_date - today).days
            if p.planned_launch_date
            else None
        )
        budget_pct = (
            float(p.budget_spent / p.budget_total * 100)
            if p.budget_total and p.budget_spent
            else None
        )

        items.append({
            "project_id": str(p.id),
            "code": p.code,
            "name": p.name,
            "current_stage": p.current_stage,
            "stage_name": stage.stage_name if stage else "—",
            "track": p.track,
            "health_status": p.health_status,
            "health_score": p.health_score,
            "progress_pct": stage.progress_pct if stage else 0,
            "planned_launch_date": p.planned_launch_date,
            "days_to_deadline": days_to_deadline,
            "budget_usage_pct": round(budget_pct, 1) if budget_pct else None,
            "status": p.status,
        })

    return {
        "total": len(items),
        "red_count":    sum(1 for i in items if i["health_status"] == "red"),
        "yellow_count": sum(1 for i in items if i["health_status"] == "yellow"),
        "green_count":  sum(1 for i in items if i["health_status"] == "green"),
        "projects": items,
    }


# ── 项目详情 ──────────────────────────────────────────────────────
@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    stages_result = await db.execute(
        select(ProjectStage)
        .where(ProjectStage.project_id == project_id)
        .order_by(ProjectStage.stage_number)
    )
    stages = stages_result.scalars().all()

    return {
        "project": {
            "id": str(project.id),
            "code": project.code,
            "name": project.name,
            "description": project.description,
            "track": project.track,
            "current_stage": project.current_stage,
            "health_status": project.health_status,
            "health_score": project.health_score,
            "planned_launch_date": project.planned_launch_date,
            "budget_total": str(project.budget_total) if project.budget_total else None,
            "budget_spent": str(project.budget_spent) if project.budget_spent else None,
            "status": project.status,
        },
        "stages": [
            {
                "id": str(s.id),
                "stage_number": s.stage_number,
                "stage_name": s.stage_name,
                "track": s.track,
                "planned_start": s.planned_start,
                "planned_end": s.planned_end,
                "actual_start": s.actual_start,
                "actual_end": s.actual_end,
                "health_status": s.health_status,
                "progress_pct": s.progress_pct,
                "health_score": s.health_score,
                "gate_passed": s.gate_passed,
                "milestones": s.milestones or [],
            }
            for s in stages
        ],
    }


# ── 甘特图数据 ───────────────────────────────────────────────────
@router.get("/{project_id}/gantt")
async def get_gantt_data(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """
    返回可直接供前端甘特图组件使用的阶段+里程碑数据。
    推荐前端搭配 react-gantt-chart 或 dhtmlx-gantt 使用。
    """
    stages_result = await db.execute(
        select(ProjectStage)
        .where(ProjectStage.project_id == project_id)
        .order_by(ProjectStage.stage_number)
    )
    stages = stages_result.scalars().all()

    return [
        GanttStage(
            stage_number=s.stage_number,
            stage_name=s.stage_name,
            track=s.track,
            planned_start=s.planned_start,
            planned_end=s.planned_end,
            actual_start=s.actual_start,
            actual_end=s.actual_end,
            progress_pct=s.progress_pct,
            health_status=s.health_status,
            gate_passed=s.gate_passed,
            milestones=s.milestones or [],
        )
        for s in stages
    ]


# ── 添加项目成员 ──────────────────────────────────────────────────
@router.post("/{project_id}/members")
async def add_project_member(
    project_id: uuid.UUID,
    data: ProjectMemberAdd,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    member = ProjectMember(
        project_id=project_id,
        user_id=data.user_id,
        track=data.track,
        role_in_project=data.role_in_project,
    )
    db.add(member)
    await db.commit()
    return {"message": "成员已加入项目", "member_id": str(member.id)}


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """项目团队成员列表"""
    from app.models.user import User
    result = await db.execute(
        select(ProjectMember, User.name, User.department)
        .join(User, ProjectMember.user_id == User.id)
        .where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.left_at.is_(None),
            )
        )
        .order_by(ProjectMember.joined_at)
    )
    return [
        {
            "id": str(r.ProjectMember.id),
            "user_id": str(r.ProjectMember.user_id),
            "name": r.name,
            "department": r.department,
            "track": r.ProjectMember.track,
            "role_in_project": r.ProjectMember.role_in_project,
            "joined_at": str(r.ProjectMember.joined_at),
        }
        for r in result.all()
    ]


# ── 更新阶段进度/里程碑 ───────────────────────────────────────────
@stages_router.patch("/{stage_id}")
async def update_stage(
    stage_id: uuid.UUID,
    data: StageUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    result = await db.execute(select(ProjectStage).where(ProjectStage.id == stage_id))
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(404, "阶段不存在")

    if data.progress_pct is not None:
        stage.progress_pct = data.progress_pct
    if data.milestones is not None:
        stage.milestones = [m.model_dump(mode="json") for m in data.milestones]
    if data.actual_start is not None:
        stage.actual_start = data.actual_start
    if data.actual_end is not None:
        stage.actual_end = data.actual_end

    await db.commit()

    # 重算项目整体健康度
    await refresh_project_health(db, stage.project_id)

    return {"message": "阶段已更新", "stage_id": str(stage_id)}
