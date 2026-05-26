"""
app/services/critical_path.py — 关键路径分析

对 Sprint 内的 task DAG 做拓扑排序 + 最长路径计算(CPM 简化版):
- 节点权重:task.story_points(若无估算用 1)
- 边:depends_on(B 依赖 A 表示 A 必须先于 B 完成)
- 关键路径:从无前置依赖到无后继依赖的最长加权路径
- 同时标记 task.is_on_critical_path = True

注意:本实现假设 DAG。若 depends_on 出现环,会跳过环上节点(而不是抛异常)。
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sprint_task import SprintTask, TaskStatus

logger = logging.getLogger("aipm.critical_path")


async def compute_critical_path(
    db: AsyncSession,
    sprint_id: UUID,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """
    返回:
      {
        "tasks": [{"id":"...", "title":"...", "weight":3, ...}, ...],
        "edges": [{"from":"a","to":"b"}, ...],
        "critical_path": ["task_id1", "task_id2", ...],  # 拓扑顺序
        "critical_length": 12,  # 总故事点
        "has_cycle": false,
      }
    """
    # V2.5 Stage 2:软删任务不参与关键路径计算
    tasks = (
        (
            await db.execute(
                select(SprintTask).where(and_(SprintTask.sprint_id == sprint_id, SprintTask.deleted_at.is_(None)))
            )
        )
        .scalars()
        .all()
    )
    if not tasks:
        return {
            "tasks": [],
            "edges": [],
            "critical_path": [],
            "critical_length": 0,
            "has_cycle": False,
        }

    by_id = {str(t.id): t for t in tasks}

    # 构建邻接表(忽略 dangling 依赖)
    out_edges: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {tid: 0 for tid in by_id}
    edges: list[dict[str, str]] = []
    for t in tasks:
        tid = str(t.id)
        for dep in t.depends_on or []:
            if dep in by_id and dep != tid:
                out_edges[dep].append(tid)
                in_degree[tid] += 1
                edges.append({"from": dep, "to": tid})

    # 拓扑排序 + 检测环
    queue = deque([tid for tid, d in in_degree.items() if d == 0])
    topo: list[str] = []
    indeg = dict(in_degree)
    while queue:
        cur = queue.popleft()
        topo.append(cur)
        for nxt in out_edges[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)

    has_cycle = len(topo) < len(by_id)
    if has_cycle:
        logger.warning("sprint %s task DAG has cycle", sprint_id)

    # DP 最长路径
    # dist[tid] 表示「从某无前置依赖的起点到 tid(含 tid 自身权重)」的最长加权路径
    dist: dict[str, float] = {tid: float(max(by_id[tid].story_points, 1)) for tid in by_id}
    prev: dict[str, str | None] = {tid: None for tid in by_id}
    for tid in topo:
        for nxt in out_edges[tid]:
            cand = dist[tid] + max(by_id[nxt].story_points, 1)
            if cand > dist[nxt]:
                dist[nxt] = cand
                prev[nxt] = tid

    # 找最长路径终点
    end_id: str | None = None
    best = -1.0
    for tid in topo:
        if dist[tid] > best:
            best = dist[tid]
            end_id = tid

    # 回溯路径 — walk / prev 字典值都是 Optional[str];循环条件已 guard
    # 注:用 walk 而非 cur 避免与上方拓扑排序循环里的 cur(str)重名
    path: list[str] = []
    walk: str | None = end_id
    while walk is not None:
        path.append(walk)
        walk = prev[walk]
    path.reverse()

    # 标记 task.is_on_critical_path
    if persist:
        on_path = set(path)
        for t in tasks:
            new_val = str(t.id) in on_path
            if t.is_on_critical_path != new_val:
                t.is_on_critical_path = new_val

    return {
        "tasks": [
            {
                "id": str(t.id),
                "title": t.title,
                "weight": t.story_points,
                "status": t.status.value,
                "priority": t.priority.value,
                "is_on_critical_path": str(t.id) in set(path),
                "assignee_id": str(t.assignee_id) if t.assignee_id else None,
                "blocked": t.status == TaskStatus.blocked,
            }
            for t in tasks
        ],
        "edges": edges,
        "critical_path": path,
        "critical_length": int(best) if best > 0 else 0,
        "has_cycle": has_cycle,
    }
