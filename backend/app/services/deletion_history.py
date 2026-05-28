"""
app/services/deletion_history.py — V2.6 软删除治理 helper

本模块只负责把"已发生的软删命中结果"记录成一条批次历史。
它不提交事务,调用方应在业务 update/delete 与历史记录写入后统一 commit。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deletion_history import DeletionHistory

SOFT_DELETE_RETENTION_DAYS = 30

TRACKED_SOFT_DELETE_TABLES = frozenset(
    {
        "daily_reports",
        "projects",
        "sprint_tasks",
        "risk_alerts",
        "knowledge_items",
    }
)


def normalize_record_ids(record_ids: Iterable[uuid.UUID | str]) -> list[str]:
    """将 UUID 输入去重并规范成小写字符串,保持原始顺序。"""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in record_ids:
        normalized_id = str(uuid.UUID(str(value)))
        if normalized_id in seen:
            continue
        seen.add(normalized_id)
        normalized.append(normalized_id)
    return normalized


def build_deletion_history(
    *,
    actor_id: Optional[uuid.UUID],
    table_name: str,
    record_ids: Iterable[uuid.UUID | str],
    deleted_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    retention_days: int = SOFT_DELETE_RETENTION_DAYS,
    tenant_id: Optional[str] = None,
) -> Optional[DeletionHistory]:
    """构造 DeletionHistory ORM 对象;空命中返回 None。"""
    if table_name not in TRACKED_SOFT_DELETE_TABLES:
        raise ValueError(f"未纳入 deletion_history 治理的表:{table_name}")

    normalized_ids = normalize_record_ids(record_ids)
    if not normalized_ids:
        return None

    effective_deleted_at = deleted_at or datetime.now(timezone.utc)
    effective_expires_at = expires_at or effective_deleted_at + timedelta(days=retention_days)

    return DeletionHistory(
        actor_id=actor_id,
        table_name=table_name,
        record_ids=normalized_ids,
        deleted_at=effective_deleted_at,
        expires_at=effective_expires_at,
        created_by=actor_id,
        tenant_id=tenant_id or "default",
    )


async def record_soft_delete(
    db: AsyncSession,
    *,
    actor_id: Optional[uuid.UUID],
    table_name: str,
    record_ids: Iterable[uuid.UUID | str],
    deleted_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    retention_days: int = SOFT_DELETE_RETENTION_DAYS,
    tenant_id: Optional[str] = None,
) -> Optional[DeletionHistory]:
    """把一次软删命中记录写入当前事务,由调用方统一 commit。"""
    history = build_deletion_history(
        actor_id=actor_id,
        table_name=table_name,
        record_ids=record_ids,
        deleted_at=deleted_at,
        expires_at=expires_at,
        retention_days=retention_days,
        tenant_id=tenant_id,
    )
    if history is None:
        return None
    db.add(history)
    return history


async def mark_soft_delete_restored(
    db: AsyncSession,
    *,
    table_name: str,
    record_ids: Iterable[uuid.UUID | str],
    restored_by: Optional[uuid.UUID],
    restored_at: Optional[datetime] = None,
    tenant_id: Optional[str] = None,
) -> int:
    """标记已完整恢复的删除批次。

    deletion_history 是"一次批量删除一条记录"。如果本次恢复只覆盖某批次的一部分
    record_ids,这里不会把整批标记为 restored,避免后续 UI 误判。
    """
    if table_name not in TRACKED_SOFT_DELETE_TABLES:
        raise ValueError(f"未纳入 deletion_history 治理的表:{table_name}")

    restored_ids = set(normalize_record_ids(record_ids))
    if not restored_ids:
        return 0

    effective_restored_at = restored_at or datetime.now(timezone.utc)
    conditions = [
        DeletionHistory.table_name == table_name,
        DeletionHistory.restored_at.is_(None),
        DeletionHistory.hard_deleted_at.is_(None),
    ]
    if tenant_id:
        conditions.append(DeletionHistory.tenant_id == tenant_id)

    rows = await db.execute(
        select(DeletionHistory).where(*conditions)
    )

    marked = 0
    for history in rows.scalars().all():
        if set(history.record_ids).issubset(restored_ids):
            history.restored_at = effective_restored_at
            history.restored_by = restored_by
            marked += 1

    return marked
