"""
app/services/sprint_aggregator.py — Sprint 数据归集与燃尽计算

功能:
- snapshot_burndown(sprint_id, snap_date=None): 为某 Sprint 写一条当日燃尽快照
- run_daily_burndown_snapshots(): 给所有 active Sprint 写当日快照(定时任务)
- compute_burndown_series(sprint_id): 生成「日期 → 理想/实际剩余点」时间序列(供前端)
- compute_velocity_history(project_id, last_n=6): 项目近 N 个已完成 Sprint 的速率历史
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import (
    BurndownSnapshot,
    SprintTask,
    TaskStatus,
)

logger = logging.getLogger("aipm.sprint_aggregator")


# ────────────────────────────────────────────────────────────────
# 单 Sprint 快照
# ────────────────────────────────────────────────────────────────


async def snapshot_burndown(
    db: AsyncSession,
    sprint_id: UUID,
    *,
    snap_date: Optional[date] = None,
) -> BurndownSnapshot:
    """计算 sprint_id 当前任务状态,落一条 BurndownSnapshot 记录"""
    if snap_date is None:
        snap_date = date.today()
    sprint = await db.get(Sprint, sprint_id)
    if not sprint:
        raise ValueError("sprint not found")
    tenant_id = sprint.tenant_id

    # V2.5 Stage 2:软删任务不计入燃尽
    tasks = (
        (
            await db.execute(
                select(SprintTask).where(
                    and_(
                        SprintTask.sprint_id == sprint_id,
                        SprintTask.tenant_id == tenant_id,
                        SprintTask.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    total_points = sum(t.story_points for t in tasks)
    done_tasks = [t for t in tasks if t.status == TaskStatus.done]
    completed_points = sum(
        (t.actual_story_points if t.actual_story_points is not None else t.story_points) for t in done_tasks
    )
    remaining_points = max(total_points - completed_points, 0)

    in_progress = sum(1 for t in tasks if t.status == TaskStatus.in_progress)
    blocked = sum(1 for t in tasks if t.status == TaskStatus.blocked)
    todo = sum(1 for t in tasks if t.status == TaskStatus.todo)

    # 同日已有快照则更新,避免重复
    existing = (
        await db.execute(
            select(BurndownSnapshot).where(
                and_(
                    BurndownSnapshot.sprint_id == sprint_id,
                    BurndownSnapshot.tenant_id == tenant_id,
                    BurndownSnapshot.snapshot_date == snap_date,
                )
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.completed_points = completed_points
        existing.remaining_points = remaining_points
        existing.total_points = total_points
        existing.done_count = len(done_tasks)
        existing.in_progress_count = in_progress
        existing.blocked_count = blocked
        existing.todo_count = todo
        return existing

    snap = BurndownSnapshot(
        sprint_id=sprint_id,
        snapshot_date=snap_date,
        completed_points=completed_points,
        remaining_points=remaining_points,
        total_points=total_points,
        done_count=len(done_tasks),
        in_progress_count=in_progress,
        blocked_count=blocked,
        todo_count=todo,
        tenant_id=tenant_id,
    )
    db.add(snap)
    return snap


# ────────────────────────────────────────────────────────────────
# 全量定时任务
# ────────────────────────────────────────────────────────────────


async def run_daily_burndown_snapshots() -> None:
    """定时任务:每日 18:00 给所有 active Sprint 写快照"""
    logger.info("⏰ [18:00] Sprint 每日燃尽快照")
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Sprint).where(Sprint.status == SprintStatus.active))).scalars().all()
        for s in rows:
            try:
                await snapshot_burndown(db, s.id)
            except Exception as exc:
                logger.exception("snapshot failed for sprint=%s: %s", s.id, exc)
        await db.commit()
        logger.info("   完成 %d 个 active Sprint 的快照", len(rows))


# ────────────────────────────────────────────────────────────────
# 燃尽序列生成(供前端绘图)
# ────────────────────────────────────────────────────────────────


async def compute_burndown_series(
    db: AsyncSession,
    sprint_id: UUID,
    *,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    返回前端 Recharts 用的燃尽序列:
    {
      "sprint": {...},
      "total_points": 40,
      "ideal_line": [{"date":"2026-05-01","points":40}, ...],
      "actual_line": [{"date":"2026-05-01","points":40,"completed":0,"blocked":0}, ...],
      "today_estimate": {"on_track": true, "projected_end_date": "2026-05-14"}
    }
    """
    sprint = await db.get(Sprint, sprint_id)
    if not sprint:
        return {"error": "sprint not found"}
    if tenant_id and sprint.tenant_id != tenant_id:
        return {"error": "sprint not found"}
    tenant = sprint.tenant_id

    start = sprint.start_date
    end = sprint.end_date
    span_days = max((end - start).days + 1, 1)

    # 任务总点数(用当前真实值,可能 sprint 进行中临时加任务)
    # V2.5 Stage 2:软删任务不计入燃尽序列总点数
    tasks = (
        (
            await db.execute(
                select(SprintTask).where(
                    and_(
                        SprintTask.sprint_id == sprint.id,
                        SprintTask.tenant_id == tenant,
                        SprintTask.deleted_at.is_(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    total_points = sum(t.story_points for t in tasks) or sprint.planned_story_points

    # 理想燃尽线:从总点数线性递减到 0
    ideal = []
    if total_points > 0:
        for i in range(span_days):
            d = start + timedelta(days=i)
            remaining = round(total_points * (1 - i / max(span_days - 1, 1)), 1)
            ideal.append({"date": d.isoformat(), "points": max(remaining, 0)})
    else:
        ideal = [{"date": start.isoformat(), "points": 0}]

    # 实际燃尽线:取所有快照,按日期升序
    snaps = (
        (
            await db.execute(
                select(BurndownSnapshot)
                .where(BurndownSnapshot.sprint_id == sprint.id, BurndownSnapshot.tenant_id == tenant)
                .order_by(BurndownSnapshot.snapshot_date)
            )
        )
        .scalars()
        .all()
    )

    actual = [
        {
            "date": s.snapshot_date.isoformat(),
            "points": s.remaining_points,
            "completed": s.completed_points,
            "blocked": s.blocked_count,
            "done_count": s.done_count,
            "in_progress_count": s.in_progress_count,
        }
        for s in snaps
    ]

    # 简单预测:基于实际线趋势外推
    today_estimate: dict[str, Any] = {}
    if len(actual) >= 2 and total_points > 0:
        first = actual[0]
        last = actual[-1]
        # actual 元素是 dict[str, Any];这里语义上 "date" 是 str / "points" 是 int
        last_date: str = str(last["date"])
        first_date: str = str(first["date"])
        first_pts: int = int(first["points"])  # type: ignore[call-overload]  # dict[str,Any] 推 object
        last_pts: int = int(last["points"])  # type: ignore[call-overload]
        days_elapsed = max(1, (date.fromisoformat(last_date) - date.fromisoformat(first_date)).days)
        burn_rate = max(0, (first_pts - last_pts)) / days_elapsed  # 每日烧多少点
        if burn_rate > 0:
            days_to_zero = last_pts / burn_rate
            projected_end = date.fromisoformat(last_date) + timedelta(days=int(days_to_zero))
            today_estimate = {
                "burn_rate_per_day": round(burn_rate, 2),
                "projected_end_date": projected_end.isoformat(),
                "planned_end_date": end.isoformat(),
                "on_track": projected_end <= end,
                "days_delta": (projected_end - end).days,
            }

    return {
        "sprint": {
            "id": str(sprint.id),
            "sprint_number": sprint.sprint_number,
            "goal": sprint.goal,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "status": sprint.status.value,
            "planned_story_points": sprint.planned_story_points,
            "completed_story_points": sprint.completed_story_points,
            "health_score": sprint.health_score,
        },
        "total_points": total_points,
        "task_count": len(tasks),
        "ideal_line": ideal,
        "actual_line": actual,
        "today_estimate": today_estimate,
    }


# ────────────────────────────────────────────────────────────────
# 项目速率历史(velocity)
# ────────────────────────────────────────────────────────────────


async def compute_velocity_history(
    db: AsyncSession,
    project_id: UUID,
    last_n: int = 6,
    *,
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """近 N 个已完成 Sprint 的速率(完成点数)历史"""
    rows = (
        (
            await db.execute(
                select(Sprint)
                .where(
                    and_(
                        Sprint.project_id == project_id,
                        Sprint.status == SprintStatus.completed,
                        *([Sprint.tenant_id == tenant_id] if tenant_id else []),
                    )
                )
                .order_by(desc(Sprint.end_date))
                .limit(last_n)
            )
        )
        .scalars()
        .all()
    )

    items = [
        {
            "sprint_number": s.sprint_number,
            "planned": s.planned_story_points,
            "completed": s.completed_story_points,
            "end_date": s.end_date.isoformat(),
            "health_score": s.health_score,
        }
        for s in reversed(rows)
    ]
    # items 是 list[dict[str, Any]];i["completed"] 推 object,实际是 int
    avg = (
        round(sum(int(i["completed"]) for i in items) / len(items), 1)  # type: ignore[call-overload]
        if items
        else 0
    )
    return {
        "project_id": str(project_id),
        "history": items,
        "avg_velocity": avg,
        "count": len(items),
    }
