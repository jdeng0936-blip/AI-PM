"""
app/services/capacity_engine.py — 资源负载水位计算引擎

核心能力:
- compute_user_capacity(user, sprint): 计算单人单 Sprint 的水位
- snapshot_sprint_capacity(sprint): 把该 Sprint 所有相关人员的水位落库
- run_weekly_capacity_refresh(): 周一定时任务,刷新所有 active Sprint
- find_overloaded / find_underutilized: 查询过载/闲置人员
- suggest_rebalance: 跨人员的任务调配建议(过载 → 闲置)
- department_capacity_summary: 部门级聚合

水位等级阈值(与白皮书 §7.2 一致):
- idle:      < 30%
- healthy:   30% ~ 80%
- high:      80% ~ 100%
- overload:  ≥ 100%
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.capacity import CapacityLevel, CapacitySnapshot
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import SprintTask, TaskStatus
from app.models.user import User, UserStatus

logger = logging.getLogger("aipm.capacity")


# ────────────────────────────────────────────────────────────────
# 工具
# ────────────────────────────────────────────────────────────────


def classify_level(utilization: float) -> CapacityLevel:
    if utilization >= 1.0:
        return CapacityLevel.overload
    if utilization >= 0.8:
        return CapacityLevel.high
    if utilization >= 0.3:
        return CapacityLevel.healthy
    return CapacityLevel.idle


async def compute_velocity_factor(
    db: AsyncSession, user_id: UUID, last_n: int = 4,
) -> float:
    """
    velocity_factor = 历史平均完成点 / 标称容量
    无历史时返回 1.0(默认完美匹配)
    使用最近 last_n 个用户作为 assignee 的 done 任务统计

    简化处理:此处用「最近 N 个 sprint 内,该用户 done 任务的总实际点 / sprint 数」估算
    """
    user = await db.get(User, user_id)
    if not user:
        return 1.0
    base = max(user.story_points_capacity, 1)

    # 拉最近 N 个完成的 sprint 中该用户的 done 任务
    sprints = (
        await db.execute(
            select(Sprint)
            .where(Sprint.status == SprintStatus.completed)
            .order_by(desc(Sprint.end_date))
            .limit(last_n * 3)  # 该用户不一定每个 sprint 都参与,多拉一些
        )
    ).scalars().all()
    if not sprints:
        return 1.0

    sprint_ids = [s.id for s in sprints]
    rows = (
        await db.execute(
            select(SprintTask)
            .where(
                and_(
                    SprintTask.assignee_id == user_id,
                    SprintTask.sprint_id.in_(sprint_ids),
                    SprintTask.status == TaskStatus.done,
                )
            )
        )
    ).scalars().all()
    if not rows:
        return 1.0

    # 按 sprint 分组求和,取均值
    by_sprint: dict[UUID, int] = {}
    for t in rows:
        pts = t.actual_story_points if t.actual_story_points is not None else t.story_points
        by_sprint[t.sprint_id] = by_sprint.get(t.sprint_id, 0) + pts

    if not by_sprint:
        return 1.0
    avg_done = sum(by_sprint.values()) / len(by_sprint)
    factor = avg_done / base
    # 控制在合理区间(防止历史样本太小造成的剧烈摆动)
    return round(max(0.5, min(factor, 1.8)), 2)


# ────────────────────────────────────────────────────────────────
# 单人单 Sprint 计算
# ────────────────────────────────────────────────────────────────


async def compute_user_capacity(
    db: AsyncSession,
    user: User,
    sprint: Sprint,
    *,
    apply_velocity: bool = True,
) -> dict[str, Any]:
    """计算单人单 Sprint 水位指标,返回 dict(不落库)"""
    tasks = (
        await db.execute(
            select(SprintTask).where(
                and_(
                    SprintTask.sprint_id == sprint.id,
                    SprintTask.assignee_id == user.id,
                )
            )
        )
    ).scalars().all()

    active_tasks = [
        t for t in tasks
        if t.status in (TaskStatus.todo, TaskStatus.in_progress, TaskStatus.blocked)
    ]
    done_tasks = [t for t in tasks if t.status == TaskStatus.done]

    allocated = sum(t.story_points for t in active_tasks)
    completed = sum(
        (t.actual_story_points if t.actual_story_points is not None else t.story_points)
        for t in done_tasks
    )
    blocked_count = sum(1 for t in active_tasks if t.status == TaskStatus.blocked)
    cp_count = sum(1 for t in tasks if t.is_on_critical_path)

    base_capacity = max(user.story_points_capacity, 1)

    # 用户状态折减(休假/出差减为 0,病假减半)
    status_factor = 1.0
    if user.status == UserStatus.on_leave:
        status_factor = 0.0
    elif user.status == UserStatus.on_travel:
        status_factor = 0.5
    elif user.status == UserStatus.sick_leave:
        status_factor = 0.3

    velocity_factor = (
        await compute_velocity_factor(db, user.id) if apply_velocity else 1.0
    )

    effective_capacity = max(int(round(base_capacity * status_factor * velocity_factor)), 0)

    if effective_capacity > 0:
        utilization = round(allocated / effective_capacity, 2)
    elif allocated > 0:
        # 容量为 0 但有任务,视为极度过载
        utilization = 2.0
    else:
        utilization = 0.0

    level = classify_level(utilization)

    return {
        "user_id": str(user.id),
        "user_name": user.name,
        "department": user.department,
        "user_status": user.status.value if hasattr(user.status, "value") else str(user.status),
        "base_capacity": base_capacity,
        "effective_capacity": effective_capacity,
        "velocity_factor": velocity_factor,
        "status_factor": status_factor,
        "allocated_points": allocated,
        "completed_points": completed,
        "active_task_count": len(active_tasks),
        "blocked_task_count": blocked_count,
        "critical_path_task_count": cp_count,
        "utilization": utilization,
        "level": level.value,
        "active_tasks": [
            {
                "id": str(t.id),
                "title": t.title,
                "story_points": t.story_points,
                "status": t.status.value,
                "priority": t.priority.value,
                "is_on_critical_path": t.is_on_critical_path,
            }
            for t in active_tasks
        ],
    }


# ────────────────────────────────────────────────────────────────
# 单 Sprint 全员快照
# ────────────────────────────────────────────────────────────────


async def snapshot_sprint_capacity(
    db: AsyncSession, sprint_id: UUID, *, include_unassigned: bool = False,
) -> list[CapacitySnapshot]:
    """
    给某 Sprint 内有任务分配的所有用户写一条 CapacitySnapshot。
    同(user, sprint)幂等(更新而非新增)。
    """
    sprint = await db.get(Sprint, sprint_id)
    if not sprint:
        return []

    # 找出有任务分配的所有用户
    user_ids_rows = (
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
    user_ids = [r[0] for r in user_ids_rows]
    if not user_ids:
        return []

    users = (
        await db.execute(select(User).where(User.id.in_(user_ids)))
    ).scalars().all()

    results: list[CapacitySnapshot] = []
    for user in users:
        metrics = await compute_user_capacity(db, user, sprint)
        # 幂等写入
        existing = (
            await db.execute(
                select(CapacitySnapshot).where(
                    and_(
                        CapacitySnapshot.user_id == user.id,
                        CapacitySnapshot.sprint_id == sprint_id,
                    )
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.base_capacity = metrics["base_capacity"]
            existing.effective_capacity = metrics["effective_capacity"]
            existing.velocity_factor = metrics["velocity_factor"]
            existing.allocated_points = metrics["allocated_points"]
            existing.completed_points = metrics["completed_points"]
            existing.active_task_count = metrics["active_task_count"]
            existing.blocked_task_count = metrics["blocked_task_count"]
            existing.critical_path_task_count = metrics["critical_path_task_count"]
            existing.utilization = metrics["utilization"]
            existing.level = CapacityLevel(metrics["level"])
            results.append(existing)
        else:
            snap = CapacitySnapshot(
                user_id=user.id,
                sprint_id=sprint_id,
                base_capacity=metrics["base_capacity"],
                effective_capacity=metrics["effective_capacity"],
                velocity_factor=metrics["velocity_factor"],
                allocated_points=metrics["allocated_points"],
                completed_points=metrics["completed_points"],
                active_task_count=metrics["active_task_count"],
                blocked_task_count=metrics["blocked_task_count"],
                critical_path_task_count=metrics["critical_path_task_count"],
                utilization=metrics["utilization"],
                level=CapacityLevel(metrics["level"]),
            )
            db.add(snap)
            results.append(snap)

    return results


# ────────────────────────────────────────────────────────────────
# 定时任务:每周一 08:30 刷新所有 active Sprint
# ────────────────────────────────────────────────────────────────


async def run_weekly_capacity_refresh() -> None:
    logger.info("⏰ [周一 08:30] 资源水位刷新")
    async with AsyncSessionLocal() as db:
        active_sprints = (
            await db.execute(
                select(Sprint).where(Sprint.status == SprintStatus.active)
            )
        ).scalars().all()
        total_snapshots = 0
        for s in active_sprints:
            try:
                rows = await snapshot_sprint_capacity(db, s.id)
                total_snapshots += len(rows)
            except Exception:
                logger.exception("capacity snapshot failed for sprint=%s", s.id)
        await db.commit()

        # 过载预警通知
        await _push_overload_alerts(db)

        logger.info(
            "   完成 %d 个 active Sprint 的水位快照,共 %d 条用户记录",
            len(active_sprints), total_snapshots,
        )


async def _push_overload_alerts(db: AsyncSession) -> None:
    """对当前 overload 的人员推送预警给管理层(企微/钉钉群机器人)"""
    rows = (
        await db.execute(
            select(CapacitySnapshot, User)
            .join(User, CapacitySnapshot.user_id == User.id)
            .where(CapacitySnapshot.level == CapacityLevel.overload)
            .order_by(desc(CapacitySnapshot.utilization))
            .limit(20)
        )
    ).all()
    if not rows:
        return

    from app.models.notification import NotificationChannel, NotificationTemplate
    from app.services.notification_service import notify_safe

    lines = []
    for snap, u in rows:
        lines.append(
            f"- **{u.name}**({u.department}): {int(snap.utilization * 100)}% "
            f"({snap.allocated_points}/{snap.effective_capacity}pt)"
            f"{', ⚠️' + str(snap.blocked_count) + '阻塞' if snap.blocked_count else ''}"
        )
    md = (
        f"### 🌡️ 资源水位过载预警\n\n"
        f"当前有 **{len(rows)}** 位成员处于过载状态(占用 ≥ 100%):\n\n"
        + "\n".join(lines)
        + "\n\n建议管理层及时调配,或前往「资源水位」页面查看 AI 调配建议。"
    )

    admins = (
        await db.execute(
            select(User).where(
                User.role.in_(["admin", "manager"]),
                User.is_active == True,
            )
        )
    ).scalars().all()

    for admin in admins:
        await notify_safe(
            db,
            template=NotificationTemplate.risk_alert,
            context={
                "name": "资源水位",
                "department": "全公司",
                "alert_type": "overload",
                "description": md,
                "days_unresolved": 0,
            },
            user=admin,
            channels=[
                NotificationChannel.wechat_bot,
                NotificationChannel.dingtalk_bot,
                NotificationChannel.in_app,
            ],
            related_type="capacity_overload",
        )


# ────────────────────────────────────────────────────────────────
# 查询:过载 / 闲置
# ────────────────────────────────────────────────────────────────


async def find_overloaded(
    db: AsyncSession, *, sprint_id: Optional[UUID] = None, limit: int = 20,
) -> list[dict[str, Any]]:
    """查询当前过载人员(可选限定某 Sprint)"""
    stmt = (
        select(CapacitySnapshot, User)
        .join(User, CapacitySnapshot.user_id == User.id)
        .where(CapacitySnapshot.level == CapacityLevel.overload)
    )
    if sprint_id:
        stmt = stmt.where(CapacitySnapshot.sprint_id == sprint_id)
    stmt = stmt.order_by(desc(CapacitySnapshot.utilization)).limit(limit)

    rows = (await db.execute(stmt)).all()
    return [_snapshot_to_dict(s, u) for s, u in rows]


async def find_underutilized(
    db: AsyncSession, *, sprint_id: Optional[UUID] = None, limit: int = 20,
) -> list[dict[str, Any]]:
    """查询当前闲置人员(level=idle)"""
    stmt = (
        select(CapacitySnapshot, User)
        .join(User, CapacitySnapshot.user_id == User.id)
        .where(CapacitySnapshot.level == CapacityLevel.idle)
    )
    if sprint_id:
        stmt = stmt.where(CapacitySnapshot.sprint_id == sprint_id)
    stmt = stmt.order_by(CapacitySnapshot.utilization).limit(limit)

    rows = (await db.execute(stmt)).all()
    return [_snapshot_to_dict(s, u) for s, u in rows]


def _snapshot_to_dict(snap: CapacitySnapshot, user: User) -> dict[str, Any]:
    return {
        "user_id": str(user.id),
        "user_name": user.name,
        "department": user.department,
        "sprint_id": str(snap.sprint_id),
        "base_capacity": snap.base_capacity,
        "effective_capacity": snap.effective_capacity,
        "velocity_factor": snap.velocity_factor,
        "allocated_points": snap.allocated_points,
        "completed_points": snap.completed_points,
        "active_task_count": snap.active_task_count,
        "blocked_task_count": snap.blocked_task_count,
        "critical_path_task_count": snap.critical_path_task_count,
        "utilization": snap.utilization,
        "level": snap.level.value,
        "suggestion": snap.suggestion,
    }


# ────────────────────────────────────────────────────────────────
# 调配建议
# ────────────────────────────────────────────────────────────────


async def suggest_rebalance(
    db: AsyncSession, sprint_id: UUID,
) -> dict[str, Any]:
    """
    生成 Sprint 内的任务调配建议:
    - 找出 overload 成员的"非关键路径 + todo"任务
    - 找出同部门 idle 成员
    - 配对建议:把任务转给 idle 成员
    返回结构:
      {
        "overloaded": [...],
        "idle": [...],
        "moves": [{"task_id":"...","title":"...","from_user":"...","to_user":"...","points":3}, ...]
      }
    """
    overloaded = await find_overloaded(db, sprint_id=sprint_id, limit=50)
    idle = await find_underutilized(db, sprint_id=sprint_id, limit=50)

    if not overloaded or not idle:
        return {"overloaded": overloaded, "idle": idle, "moves": []}

    # 同部门优先匹配
    idle_by_dept: dict[str, list[dict]] = {}
    for u in idle:
        idle_by_dept.setdefault(u["department"] or "", []).append(u)

    moves: list[dict[str, Any]] = []

    for over in overloaded:
        # 该过载成员的可移动任务:非关键路径 + 状态 todo,按点数降序
        tasks = (
            await db.execute(
                select(SprintTask).where(
                    and_(
                        SprintTask.sprint_id == sprint_id,
                        SprintTask.assignee_id == UUID(over["user_id"]),
                        SprintTask.status == TaskStatus.todo,
                        SprintTask.is_on_critical_path.is_(False),
                    )
                )
                .order_by(desc(SprintTask.story_points))
            )
        ).scalars().all()
        if not tasks:
            continue

        # 候选接收方:同部门 idle,按剩余容量降序
        candidates = sorted(
            idle_by_dept.get(over["department"] or "", []),
            key=lambda u: (u["effective_capacity"] - u["allocated_points"]),
            reverse=True,
        ) or sorted(
            idle,  # 跨部门兜底
            key=lambda u: (u["effective_capacity"] - u["allocated_points"]),
            reverse=True,
        )
        if not candidates:
            continue

        # 简单贪心:把过载成员超出 80% 的部分挪给闲置成员
        need_to_move = max(
            int(over["allocated_points"] - over["effective_capacity"] * 0.8), 0
        )
        moved_points = 0
        for task in tasks:
            if moved_points >= need_to_move:
                break
            # 找一个还有空余容量的接收方
            target = None
            for cand in candidates:
                room = cand["effective_capacity"] - cand["allocated_points"]
                if room >= task.story_points:
                    target = cand
                    break
            if not target:
                continue
            moves.append(
                {
                    "task_id": str(task.id),
                    "title": task.title,
                    "points": task.story_points,
                    "from_user": over["user_name"],
                    "from_user_id": over["user_id"],
                    "to_user": target["user_name"],
                    "to_user_id": target["user_id"],
                    "department_match": target["department"] == over["department"],
                }
            )
            # 更新候选方的已分配点(下一轮匹配考虑)
            target["allocated_points"] += task.story_points
            moved_points += task.story_points

    return {
        "overloaded": overloaded,
        "idle": idle,
        "moves": moves,
    }


# ────────────────────────────────────────────────────────────────
# 部门聚合
# ────────────────────────────────────────────────────────────────


async def department_capacity_summary(
    db: AsyncSession, *, sprint_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """部门级水位聚合(适合 admin 总览)"""
    stmt = (
        select(
            User.department,
            func.count(CapacitySnapshot.id).label("member_count"),
            func.sum(CapacitySnapshot.effective_capacity).label("total_capacity"),
            func.sum(CapacitySnapshot.allocated_points).label("total_allocated"),
            func.sum(CapacitySnapshot.completed_points).label("total_completed"),
            func.avg(CapacitySnapshot.utilization).label("avg_util"),
        )
        .join(User, CapacitySnapshot.user_id == User.id)
        .group_by(User.department)
    )
    if sprint_id:
        stmt = stmt.where(CapacitySnapshot.sprint_id == sprint_id)

    rows = (await db.execute(stmt)).all()
    departments = []
    for r in rows:
        cap = int(r.total_capacity or 0)
        alloc = int(r.total_allocated or 0)
        util = round(alloc / cap, 2) if cap > 0 else 0.0
        departments.append(
            {
                "department": r.department or "(未分组)",
                "member_count": int(r.member_count),
                "total_capacity": cap,
                "total_allocated": alloc,
                "total_completed": int(r.total_completed or 0),
                "utilization": util,
                "level": classify_level(util).value,
                "avg_member_util": round(float(r.avg_util or 0), 2),
            }
        )
    departments.sort(key=lambda d: d["utilization"], reverse=True)
    return {"departments": departments, "count": len(departments)}
