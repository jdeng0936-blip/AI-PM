"""
app/routers/me_deletions.py — 我的最近删除

V2.6 Stage 5:普通用户可查看并恢复自己最近 30 天内执行的软删批次。
不暴露其他人的 deletion_history,也不暴露原始 record_ids。
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user
from app.models.daily_report import DailyReport
from app.models.deletion_history import DeletionHistory
from app.models.knowledge import KnowledgeItem
from app.models.project import Project
from app.models.risk_alert import RiskAlert
from app.models.sprint_task import SprintTask
from app.models.user import User
from app.services.deletion_history import mark_soft_delete_restored
from app.services.sprint_aggregator import snapshot_burndown

router = APIRouter(prefix="/api/v1/me/deletions", tags=["Me / Deletions"])

RECENT_DELETION_DAYS = 30


class MyDeletionBatchOut(BaseModel):
    id: str
    table_name: str
    record_ids: int
    record_count: int
    deleted_at: str
    expires_at: str
    restored_at: Optional[str]
    restored_by: Optional[str]
    days_remaining: Optional[int]


class MyDeletionsResponse(BaseModel):
    items: list[MyDeletionBatchOut]
    total: int


class RestoreDeletionResponse(BaseModel):
    restored_count: int
    table_name: str
    batch_id: str


def _days_remaining(history: DeletionHistory, now: datetime) -> Optional[int]:
    """已恢复批次不显示倒计时;未恢复时向上取整到天。"""
    if history.restored_at is not None:
        return None
    seconds = (history.expires_at - now).total_seconds()
    return max(0, math.ceil(seconds / 86_400))


def _can_restore_batch(history: DeletionHistory, user: User) -> bool:
    """个人恢复只允许本人、未恢复、未硬删的删除批次。"""
    return history.actor_id == user.id and history.restored_at is None and history.hard_deleted_at is None


def _parse_record_ids(history: DeletionHistory) -> list[uuid.UUID]:
    try:
        return [uuid.UUID(str(record_id)) for record_id in history.record_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "删除历史中的 record_ids 格式不正确") from exc


async def _restore_records_for_history(db: AsyncSession, history: DeletionHistory) -> tuple[int, set[uuid.UUID]]:
    """按 deletion_history.table_name 恢复业务表;返回恢复数量与受影响 sprint 集合。"""
    record_ids = _parse_record_ids(history)
    if not record_ids:
        return 0, set()

    if history.table_name == "daily_reports":
        result = await db.execute(
            update(DailyReport)
            .where(and_(DailyReport.id.in_(record_ids), DailyReport.deleted_at.is_not(None)))
            .values(deleted_at=None)
            .returning(DailyReport.id)
        )
        return len(result.all()), set()

    if history.table_name == "projects":
        result = await db.execute(
            update(Project)
            .where(and_(Project.id.in_(record_ids), Project.deleted_at.is_not(None), Project.is_temporary.is_(True)))
            .values(deleted_at=None)
            .returning(Project.id)
        )
        return len(result.all()), set()

    if history.table_name == "sprint_tasks":
        pre_rows = (
            await db.execute(
                select(SprintTask.id, SprintTask.sprint_id).where(
                    and_(SprintTask.id.in_(record_ids), SprintTask.deleted_at.is_not(None))
                )
            )
        ).all()
        sprint_ids = {row.sprint_id for row in pre_rows}
        result = await db.execute(
            update(SprintTask)
            .where(and_(SprintTask.id.in_(record_ids), SprintTask.deleted_at.is_not(None)))
            .values(deleted_at=None)
            .returning(SprintTask.id)
        )
        return len(result.all()), sprint_ids

    if history.table_name == "risk_alerts":
        result = await db.execute(
            update(RiskAlert)
            .where(and_(RiskAlert.id.in_(record_ids), RiskAlert.deleted_at.is_not(None)))
            .values(deleted_at=None)
            .returning(RiskAlert.id)
        )
        return len(result.all()), set()

    if history.table_name == "knowledge_items":
        result = await db.execute(
            update(KnowledgeItem)
            .where(and_(KnowledgeItem.id.in_(record_ids), KnowledgeItem.deleted_at.is_not(None)))
            .values(deleted_at=None)
            .returning(KnowledgeItem.id)
        )
        return len(result.all()), set()

    raise HTTPException(400, f"不支持恢复表:{history.table_name}")


def _batch_out(history: DeletionHistory, now: datetime) -> MyDeletionBatchOut:
    return MyDeletionBatchOut(
        id=str(history.id),
        table_name=history.table_name,
        record_ids=len(history.record_ids),
        record_count=len(history.record_ids),
        deleted_at=history.deleted_at.isoformat(),
        expires_at=history.expires_at.isoformat(),
        restored_at=history.restored_at.isoformat() if history.restored_at else None,
        restored_by=str(history.restored_by) if history.restored_by else None,
        days_remaining=_days_remaining(history, now),
    )


@router.get("", response_model=MyDeletionsResponse)
@router.get("/", response_model=MyDeletionsResponse)
async def list_my_deletions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """最近 30 天内当前用户自己执行的删除批次。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_DELETION_DAYS)
    rows = await db.execute(
        select(DeletionHistory)
        .where(
            DeletionHistory.actor_id == current_user.id,
            DeletionHistory.hard_deleted_at.is_(None),
            DeletionHistory.deleted_at >= cutoff,
        )
        .order_by(DeletionHistory.deleted_at.desc())
    )
    items = [_batch_out(history, now) for history in rows.scalars().all()]
    return MyDeletionsResponse(items=items, total=len(items))


@router.patch("/{batch_id}/restore", response_model=RestoreDeletionResponse)
async def restore_my_deletion_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """恢复当前用户自己的一个删除批次。"""
    history = await db.get(DeletionHistory, batch_id)
    if not history:
        raise HTTPException(404, "删除批次不存在")
    if history.actor_id != current_user.id:
        raise HTTPException(403, "不能恢复其他人的删除批次")
    if history.restored_at is not None:
        raise HTTPException(400, "该删除批次已恢复")
    if history.hard_deleted_at is not None:
        raise HTTPException(400, "该删除批次已过期清理")
    if not _can_restore_batch(history, current_user):
        raise HTTPException(403, "不能恢复该删除批次")

    restored_count, affected_sprint_ids = await _restore_records_for_history(db, history)
    await mark_soft_delete_restored(
        db,
        table_name=history.table_name,
        record_ids=history.record_ids,
        restored_by=current_user.id,
    )
    for sprint_id in affected_sprint_ids:
        await snapshot_burndown(db, sprint_id)
    await db.commit()

    return RestoreDeletionResponse(
        restored_count=restored_count,
        table_name=history.table_name,
        batch_id=str(history.id),
    )
