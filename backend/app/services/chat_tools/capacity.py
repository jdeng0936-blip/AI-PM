"""
chat_tools/capacity.py — 资源水位 Chat Tools

供总经理 AI 对话使用:
- workload_status        某项目当前 Sprint 全员水位概况
- list_overloaded        当前过载人员名单
- list_underutilized     当前闲置人员名单
- rebalance_suggestion   某 Sprint 任务调配建议
- department_workload    部门级水位聚合
"""

from __future__ import annotations

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.sprint import Sprint, SprintStatus
from app.services.capacity_engine import (
    compute_user_capacity,
    department_capacity_summary,
    find_overloaded,
    find_underutilized,
    suggest_rebalance,
)
from app.services.chat_tools import tool


async def _find_active_sprint(db: AsyncSession, project_query: str, tenant_id: str) -> tuple:
    """返回 (project, sprint) 或 (None, None)"""
    q = project_query.strip()
    if not q:
        return None, None
    proj = (
        await db.execute(
            select(Project)
            .where(
                Project.tenant_id == tenant_id,
                Project.deleted_at.is_(None),
                or_(Project.name.ilike(f"%{q}%"), Project.code.ilike(f"%{q}%")),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if not proj:
        return None, None
    sprint = (
        await db.execute(
            select(Sprint)
            .where(Sprint.project_id == proj.id, Sprint.tenant_id == tenant_id, Sprint.status == SprintStatus.active)
            .order_by(desc(Sprint.start_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    return proj, sprint


@tool(description="某项目当前 active Sprint 的全员资源水位概况(过载/健康/闲置分布)")
async def workload_status(
    db: AsyncSession,
    project_query: str,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        project_query: 项目名称或编号
    """
    proj, sprint = await _find_active_sprint(db, project_query, tenant_id)
    if not proj:
        return {"error": f"未找到项目 『{project_query}』"}
    if not sprint:
        return {"project": proj.name, "message": "当前无 active Sprint"}

    from app.models.sprint_task import SprintTask
    from app.models.user import User

    user_ids = [
        r[0]
        for r in (
            await db.execute(
                select(SprintTask.assignee_id)
                .where(
                    and_(
                        SprintTask.sprint_id == sprint.id,
                        SprintTask.tenant_id == tenant_id,
                        SprintTask.assignee_id.is_not(None),
                        SprintTask.deleted_at.is_(None),  # V2.5 Stage 2
                    )
                )
                .distinct()
            )
        ).all()
    ]
    if not user_ids:
        return {"project": proj.name, "message": "Sprint 内无任务分配"}

    users = (await db.execute(select(User).where(User.id.in_(user_ids), User.tenant_id == tenant_id))).scalars().all()
    members = [await compute_user_capacity(db, u, sprint) for u in users]
    members.sort(key=lambda m: m["utilization"], reverse=True)

    by_level = {"overload": 0, "high": 0, "healthy": 0, "idle": 0}
    for m in members:
        by_level[m["level"]] = by_level.get(m["level"], 0) + 1

    return {
        "project": {"code": proj.code, "name": proj.name},
        "sprint": {
            "id": str(sprint.id),
            "sprint_number": sprint.sprint_number,
            "goal": sprint.goal,
        },
        "member_count": len(members),
        "distribution": by_level,
        # 只回传 Top 5 过载和闲置,避免上下文爆炸
        "top_overloaded": [
            {
                "name": m["user_name"],
                "department": m["department"],
                "utilization": m["utilization"],
                "allocated": m["allocated_points"],
                "capacity": m["effective_capacity"],
            }
            for m in members
            if m["level"] == "overload"
        ][:5],
        "top_idle": [
            {
                "name": m["user_name"],
                "department": m["department"],
                "utilization": m["utilization"],
                "free_capacity": m["effective_capacity"] - m["allocated_points"],
            }
            for m in members
            if m["level"] == "idle"
        ][:5],
    }


@tool(description="列出当前(快照表中)过载的人员名单,按占用率降序")
async def list_overloaded_members(
    db: AsyncSession,
    limit: int = 10,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        limit: 返回前 N 人
    """
    items = await find_overloaded(db, limit=limit, tenant_id=tenant_id)
    return {
        "count": len(items),
        "items": [
            {
                "name": x["user_name"],
                "department": x["department"],
                "utilization": x["utilization"],
                "allocated_points": x["allocated_points"],
                "effective_capacity": x["effective_capacity"],
                "blocked_task_count": x["blocked_task_count"],
                "critical_path_task_count": x["critical_path_task_count"],
            }
            for x in items
        ],
    }


@tool(description="列出当前(快照表中)闲置的人员名单(占用 < 30%),按占用率升序")
async def list_underutilized_members(
    db: AsyncSession,
    limit: int = 10,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        limit: 返回前 N 人
    """
    items = await find_underutilized(db, limit=limit, tenant_id=tenant_id)
    return {
        "count": len(items),
        "items": [
            {
                "name": x["user_name"],
                "department": x["department"],
                "utilization": x["utilization"],
                "free_capacity": x["effective_capacity"] - x["allocated_points"],
                "active_task_count": x["active_task_count"],
            }
            for x in items
        ],
    }


@tool(description="某项目当前 Sprint 的 AI 任务调配建议(过载 → 闲置)")
async def rebalance_suggestion(
    db: AsyncSession,
    project_query: str,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        project_query: 项目名称或编号
    """
    proj, sprint = await _find_active_sprint(db, project_query, tenant_id)
    if not proj:
        return {"error": f"未找到项目 『{project_query}』"}
    if not sprint:
        return {"project": proj.name, "message": "当前无 active Sprint"}

    result = await suggest_rebalance(db, sprint.id, tenant_id=tenant_id)
    # 精简:只回传 moves
    return {
        "project": {"code": proj.code, "name": proj.name},
        "sprint_number": sprint.sprint_number,
        "overloaded_count": len(result["overloaded"]),
        "idle_count": len(result["idle"]),
        "move_count": len(result["moves"]),
        "moves": result["moves"],
    }


@tool(description="部门级资源水位聚合(每个部门一行 + 整体占用率)")
async def department_workload(
    db: AsyncSession,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        (no args)
    """
    return await department_capacity_summary(db, tenant_id=tenant_id)
