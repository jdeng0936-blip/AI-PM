"""
chat_tools/projects.py — 项目与风险查询 Tools
"""

from __future__ import annotations

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus
from app.models.risk_alert import RiskAlert
from app.models.user import User
from app.services.chat_tools import tool


@tool(description="按名称或编号模糊匹配查询单个项目的状态(健康度/进度/预算)")
async def get_project_status(
    db: AsyncSession,
    project_query: str,
) -> dict:
    """
    Args:
        project_query: 项目名称关键字或编号(如「206」「P2026-001」)
    """
    q = project_query.strip()
    if not q:
        return {"error": "project_query 不能为空"}

    stmt = select(Project).where(or_(Project.name.ilike(f"%{q}%"), Project.code.ilike(f"%{q}%"))).limit(5)
    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        return {"matched": [], "message": f"未找到匹配 『{q}』 的项目"}

    items = []
    for p in rows:
        items.append(
            {
                "code": p.code,
                "name": p.name,
                "track": p.track.value if p.track else None,
                "current_stage": p.current_stage,
                "status": p.status.value if p.status else None,
                "health_status": p.health_status.value if p.health_status else None,
                "health_score": p.health_score,
                "planned_launch_date": p.planned_launch_date.isoformat() if p.planned_launch_date else None,
                "actual_launch_date": p.actual_launch_date.isoformat() if p.actual_launch_date else None,
                "budget_total": float(p.budget_total) if p.budget_total else None,
                "budget_spent": float(p.budget_spent) if p.budget_spent else None,
            }
        )
    return {"matched": items, "count": len(items)}


@tool(description="列出当前所有未解决的风险预警,按未解决天数降序")
async def list_active_risks(
    db: AsyncSession,
    limit: int = 20,
    department: str = "",
    alert_type: str = "",
) -> dict:
    """
    Args:
        limit: 返回前 N 条,默认 20
        department: 限定部门,空=全部
        alert_type: 限定类型(blocker/dependency/recurring),空=全部
    """
    stmt = (
        select(
            RiskAlert.id,
            RiskAlert.alert_type,
            RiskAlert.description,
            RiskAlert.days_unresolved,
            RiskAlert.created_at,
            User.name,
            User.department,
        )
        .join(User, RiskAlert.user_id == User.id)
        .where(
            RiskAlert.status == "unresolved",
            RiskAlert.deleted_at.is_(None),  # V2.5 Stage 3:软删过滤
        )
    )
    if department:
        stmt = stmt.where(User.department == department)
    if alert_type:
        stmt = stmt.where(RiskAlert.alert_type == alert_type)

    stmt = stmt.order_by(desc(RiskAlert.days_unresolved)).limit(limit)
    rows = (await db.execute(stmt)).all()

    return {
        "count": len(rows),
        "items": [
            {
                "id": str(r.id),
                "user": r.name,
                "department": r.department,
                "alert_type": r.alert_type,
                "description": r.description[:200],
                "days_unresolved": int(r.days_unresolved),
                "raised_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@tool(description="项目组合视图:所有活跃项目的健康度概览,按健康分升序(差的优先看)")
async def list_active_projects(db: AsyncSession, limit: int = 30) -> dict:
    """
    Args:
        limit: 返回数量上限,默认 30
    """
    stmt = select(Project).where(Project.status == ProjectStatus.active).order_by(Project.health_score).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "count": len(rows),
        "projects": [
            {
                "code": p.code,
                "name": p.name,
                "current_stage": p.current_stage,
                "health_status": p.health_status.value if p.health_status else None,
                "health_score": p.health_score,
                "planned_launch_date": p.planned_launch_date.isoformat() if p.planned_launch_date else None,
            }
            for p in rows
        ],
    }


@tool(description="项目健康度三色分布(红/黄/绿各多少个),用于战情概览")
async def project_health_distribution(db: AsyncSession) -> dict:
    """
    Args:
        (no args)
    """
    stmt = (
        select(Project.health_status, func.count(Project.id))
        .where(Project.status == ProjectStatus.active)
        .group_by(Project.health_status)
    )
    rows = (await db.execute(stmt)).all()
    dist = {r[0].value if r[0] else "unknown": int(r[1]) for r in rows}
    total = sum(dist.values())
    return {"total_active": total, "distribution": dist}
