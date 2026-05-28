"""
chat_tools/sprints.py — Sprint 相关 Chat Tools

供总经理 AI 对话使用:
- sprint_status        某项目当前 active sprint 概况
- sprint_burndown      某 sprint 燃尽简报(剩余点 + 是否能按期完成)
- critical_path        某 sprint 关键路径上的任务
"""

from __future__ import annotations

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import SprintTask
from app.services.chat_tools import tool
from app.services.critical_path import compute_critical_path
from app.services.sprint_aggregator import (
    compute_burndown_series,
    compute_velocity_history,
)


async def _find_project(db: AsyncSession, query: str, tenant_id: str):
    if not query:
        return None
    q = query.strip()
    return (
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


@tool(description="查询某项目当前活跃 Sprint 的概况(目标 / 故事点 / 健康度 / 任务分布)")
async def sprint_status(
    db: AsyncSession,
    project_query: str,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        project_query: 项目名称或编号(如「206」「P2026-001」)
    """
    proj = await _find_project(db, project_query, tenant_id)
    if not proj:
        return {"error": f"未找到匹配 『{project_query}』 的项目"}

    sprint = (
        await db.execute(
            select(Sprint)
            .where(Sprint.project_id == proj.id, Sprint.tenant_id == tenant_id, Sprint.status == SprintStatus.active)
            .order_by(desc(Sprint.start_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    if not sprint:
        return {
            "project": {"code": proj.code, "name": proj.name},
            "message": "当前没有 active Sprint",
        }

    # V2.5 Stage 2:chat 总经理对话也按"软删过滤"语义,避免误把已删任务报进概况
    tasks = (
        (
            await db.execute(
                select(SprintTask).where(
                    and_(SprintTask.sprint_id == sprint.id, SprintTask.tenant_id == tenant_id, SprintTask.deleted_at.is_(None))
                )
            )
        )
        .scalars()
        .all()
    )

    by_status = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0, "cancelled": 0}
    for t in tasks:
        by_status[t.status.value] = by_status.get(t.status.value, 0) + 1

    return {
        "project": {"code": proj.code, "name": proj.name},
        "sprint": {
            "id": str(sprint.id),
            "sprint_number": sprint.sprint_number,
            "goal": sprint.goal,
            "start_date": sprint.start_date.isoformat(),
            "end_date": sprint.end_date.isoformat(),
            "status": sprint.status.value,
            "planned_story_points": sprint.planned_story_points,
            "completed_story_points": sprint.completed_story_points,
            "health_score": sprint.health_score,
        },
        "task_count": len(tasks),
        "task_distribution": by_status,
        "critical_path_count": sum(1 for t in tasks if t.is_on_critical_path),
    }


@tool(description="某 Sprint 的燃尽简报:剩余点数、燃烧速率、是否能按期完成")
async def sprint_burndown(
    db: AsyncSession,
    project_query: str,
    sprint_number: int = 0,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        project_query: 项目名称或编号
        sprint_number: Sprint 编号,0=取当前活跃 Sprint
    """
    proj = await _find_project(db, project_query, tenant_id)
    if not proj:
        return {"error": f"未找到项目 『{project_query}』"}

    stmt = select(Sprint).where(Sprint.project_id == proj.id, Sprint.tenant_id == tenant_id)
    if sprint_number > 0:
        stmt = stmt.where(Sprint.sprint_number == sprint_number)
    else:
        stmt = stmt.where(Sprint.status == SprintStatus.active)
    stmt = stmt.order_by(desc(Sprint.start_date)).limit(1)

    sprint = (await db.execute(stmt)).scalar_one_or_none()
    if not sprint:
        return {
            "project": {"code": proj.code, "name": proj.name},
            "message": "未找到匹配的 Sprint",
        }

    data = await compute_burndown_series(db, sprint.id, tenant_id=tenant_id)
    if "error" in data:
        return data

    # 只回传摘要,避免对话上下文爆炸
    actual = data["actual_line"]
    latest = actual[-1] if actual else None
    return {
        "sprint": data["sprint"],
        "total_points": data["total_points"],
        "snapshot_count": len(actual),
        "latest_snapshot": latest,
        "today_estimate": data["today_estimate"],
    }


@tool(description="列出某 Sprint 关键路径上的所有任务(故事点最长的依赖链)")
async def critical_path(
    db: AsyncSession,
    project_query: str,
    sprint_number: int = 0,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        project_query: 项目名称或编号
        sprint_number: Sprint 编号,0=取当前活跃 Sprint
    """
    proj = await _find_project(db, project_query, tenant_id)
    if not proj:
        return {"error": f"未找到项目 『{project_query}』"}

    stmt = select(Sprint).where(Sprint.project_id == proj.id, Sprint.tenant_id == tenant_id)
    if sprint_number > 0:
        stmt = stmt.where(Sprint.sprint_number == sprint_number)
    else:
        stmt = stmt.where(Sprint.status == SprintStatus.active)
    stmt = stmt.order_by(desc(Sprint.start_date)).limit(1)
    sprint = (await db.execute(stmt)).scalar_one_or_none()
    if not sprint:
        return {"error": "未找到 Sprint"}

    result = await compute_critical_path(db, sprint.id, persist=False)
    # 精简:只回传关键路径上的任务
    path_ids = set(result["critical_path"])
    on_path = [t for t in result["tasks"] if t["id"] in path_ids]
    blocked_on_path = [t for t in on_path if t["blocked"]]
    return {
        "sprint": {
            "id": str(sprint.id),
            "sprint_number": sprint.sprint_number,
            "goal": sprint.goal,
        },
        "critical_length_points": result["critical_length"],
        "task_count_on_path": len(on_path),
        "blocked_count_on_path": len(blocked_on_path),
        "has_cycle": result["has_cycle"],
        "path": [
            {
                "title": t["title"],
                "weight": t["weight"],
                "status": t["status"],
                "priority": t["priority"],
                "blocked": t["blocked"],
            }
            for t in on_path
        ],
    }


@tool(description="查询某项目的 Sprint 速率历史(近 N 个已完成 Sprint 的完成点数趋势)")
async def project_velocity(
    db: AsyncSession,
    project_query: str,
    last_n: int = 6,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        project_query: 项目名称或编号
        last_n: 取最近 N 个已完成 Sprint(默认 6)
    """
    proj = await _find_project(db, project_query, tenant_id)
    if not proj:
        return {"error": f"未找到项目 『{project_query}』"}

    return await compute_velocity_history(db, proj.id, last_n=last_n, tenant_id=tenant_id)
