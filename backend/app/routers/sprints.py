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
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.sprint import Sprint, SprintStatus
from app.models.user import UserRole
from app.schemas.project import SprintCreate, SprintComplete
from app.services.health_engine import refresh_sprint_health

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
    result = await db.execute(
        select(Sprint)
        .where(Sprint.project_id == project_id)
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
                round(s.completed_story_points / s.planned_story_points * 100)
                if s.planned_story_points
                else None
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
