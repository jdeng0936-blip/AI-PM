"""
chat_tools/okr.py — OKR 战略对齐查询 Tools(供总经理 AI 对话使用)

提供:
- list_active_objectives   列出当前活跃周期的所有 O
- kr_status                指定 O 或全周期的 KR 进度详情
- kr_at_risk               进度滞后的 KR(<某阈值)
- objective_snapshot       单个 Objective 的完整快照(含 KR + 最近进度变更)
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.okr import (
    KeyResult,
    KRProgressLog,
    OKRCycle,
    OKRStatus,
    Objective,
)
from app.models.user import User
from app.services.chat_tools import tool


async def _active_cycle(db: AsyncSession) -> Optional[OKRCycle]:
    return (
        await db.execute(
            select(OKRCycle)
            .where(OKRCycle.status == OKRStatus.active)
            .order_by(desc(OKRCycle.start_date))
            .limit(1)
        )
    ).scalar_one_or_none()


@tool(description="列出当前活跃 OKR 周期下的所有目标(O)及其整体进度")
async def list_active_objectives(
    db: AsyncSession,
    cycle_name: str = "",
) -> dict:
    """
    Args:
        cycle_name: 限定周期名称(如「2026Q2」),空=自动取最新 active 周期
    """
    if cycle_name:
        cycle = (
            await db.execute(
                select(OKRCycle).where(OKRCycle.name == cycle_name).limit(1)
            )
        ).scalar_one_or_none()
    else:
        cycle = await _active_cycle(db)

    if not cycle:
        return {"error": "未找到 active 周期"}

    rows = (
        await db.execute(
            select(Objective, User.name)
            .join(User, Objective.owner_id == User.id, isouter=True)
            .where(Objective.cycle_id == cycle.id)
            .order_by(desc(Objective.weight))
        )
    ).all()
    return {
        "cycle": {
            "id": str(cycle.id), "name": cycle.name,
            "start": str(cycle.start_date), "end": str(cycle.end_date),
        },
        "count": len(rows),
        "objectives": [
            {
                "id": str(o.id),
                "title": o.title,
                "owner": owner_name,
                "weight": o.weight,
                "progress": o.progress,
                "status": o.status.value,
            }
            for o, owner_name in rows
        ],
    }


@tool(description="查询某个目标下所有 KR 的详细进度(目标值、当前值、置信度)")
async def kr_status(
    db: AsyncSession,
    objective_title: str = "",
    objective_id: str = "",
) -> dict:
    """
    Args:
        objective_title: 目标标题关键字(模糊匹配),用于自然语言提问
        objective_id: 目标 UUID(精确匹配),与 objective_title 二选一
    """
    if objective_id:
        obj = await db.get(Objective, objective_id)
        matched_objs = [obj] if obj else []
    elif objective_title:
        matched_objs = (
            await db.execute(
                select(Objective)
                .where(Objective.title.ilike(f"%{objective_title}%"))
                .limit(3)
            )
        ).scalars().all()
    else:
        return {"error": "请提供 objective_title 或 objective_id"}

    if not matched_objs:
        return {"matched": [], "message": "未找到匹配的目标"}

    items = []
    for obj in matched_objs:
        krs = (
            await db.execute(
                select(KeyResult).where(KeyResult.objective_id == obj.id)
            )
        ).scalars().all()
        items.append(
            {
                "objective_id": str(obj.id),
                "objective_title": obj.title,
                "objective_progress": obj.progress,
                "kr_count": len(krs),
                "key_results": [
                    {
                        "id": str(kr.id),
                        "title": kr.title,
                        "metric_type": kr.metric_type,
                        "target_value": kr.target_value,
                        "current_value": kr.current_value,
                        "unit": kr.unit,
                        "progress": kr.progress,
                        "confidence": kr.confidence,
                    }
                    for kr in krs
                ],
            }
        )
    return {"matched": items, "count": len(items)}


@tool(description="列出当前进度滞后(低于阈值)的所有 KR,按进度升序")
async def kr_at_risk(
    db: AsyncSession,
    progress_threshold: float = 40.0,
    cycle_name: str = "",
    limit: int = 20,
) -> dict:
    """
    Args:
        progress_threshold: 进度阈值(百分比),低于此值视为滞后,默认 40
        cycle_name: 限定周期名称,空=自动取最新 active 周期
        limit: 返回前 N 条
    """
    if cycle_name:
        cycle = (
            await db.execute(
                select(OKRCycle).where(OKRCycle.name == cycle_name).limit(1)
            )
        ).scalar_one_or_none()
    else:
        cycle = await _active_cycle(db)
    if not cycle:
        return {"error": "未找到 active 周期"}

    rows = (
        await db.execute(
            select(KeyResult, Objective.title, User.name)
            .join(Objective, KeyResult.objective_id == Objective.id)
            .join(User, KeyResult.owner_id == User.id, isouter=True)
            .where(Objective.cycle_id == cycle.id)
        )
    ).all()

    at_risk = []
    for kr, obj_title, owner_name in rows:
        if kr.progress < progress_threshold:
            at_risk.append(
                {
                    "kr_id": str(kr.id),
                    "kr_title": kr.title,
                    "objective_title": obj_title,
                    "owner": owner_name,
                    "progress": kr.progress,
                    "current_value": kr.current_value,
                    "target_value": kr.target_value,
                    "unit": kr.unit,
                    "confidence": kr.confidence,
                }
            )
    at_risk.sort(key=lambda x: x["progress"])
    return {
        "cycle": cycle.name,
        "threshold": progress_threshold,
        "count": len(at_risk),
        "at_risk": at_risk[:limit],
    }


@tool(description="单个目标的完整快照:基本信息 + KR 列表 + 最近 N 条 AI/手工进度变更日志")
async def objective_snapshot(
    db: AsyncSession,
    objective_title: str,
    recent_logs_limit: int = 10,
) -> dict:
    """
    Args:
        objective_title: 目标标题关键字(模糊匹配)
        recent_logs_limit: 取最近 N 条进度变更日志,默认 10
    """
    obj = (
        await db.execute(
            select(Objective).where(Objective.title.ilike(f"%{objective_title}%")).limit(1)
        )
    ).scalar_one_or_none()
    if not obj:
        return {"error": f"未找到目标『{objective_title}』"}

    owner = await db.get(User, obj.owner_id) if obj.owner_id else None
    krs = (
        await db.execute(
            select(KeyResult).where(KeyResult.objective_id == obj.id)
        )
    ).scalars().all()
    kr_ids = [kr.id for kr in krs]

    logs = []
    if kr_ids:
        log_rows = (
            await db.execute(
                select(KRProgressLog)
                .where(KRProgressLog.kr_id.in_(kr_ids))
                .order_by(desc(KRProgressLog.created_at))
                .limit(recent_logs_limit)
            )
        ).scalars().all()
        for r in log_rows:
            logs.append(
                {
                    "kr_id": str(r.kr_id),
                    "previous": r.previous_value,
                    "new": r.new_value,
                    "source": r.source.value,
                    "confidence": r.confidence,
                    "note": (r.note or "")[:200],
                    "at": r.created_at.isoformat() if r.created_at else None,
                }
            )

    return {
        "objective": {
            "id": str(obj.id),
            "title": obj.title,
            "description": obj.description,
            "owner": owner.name if owner else None,
            "department": owner.department if owner else None,
            "weight": obj.weight,
            "progress": obj.progress,
            "status": obj.status.value,
        },
        "key_results": [
            {
                "id": str(kr.id),
                "title": kr.title,
                "current_value": kr.current_value,
                "target_value": kr.target_value,
                "unit": kr.unit,
                "progress": kr.progress,
                "confidence": kr.confidence,
            }
            for kr in krs
        ],
        "recent_progress_logs": logs,
    }
