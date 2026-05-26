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
) -> Optional[DeletionHistory]:
    """把一次软删命中记录写入当前事务,由调用方统一 commit。"""
    history = build_deletion_history(
        actor_id=actor_id,
        table_name=table_name,
        record_ids=record_ids,
        deleted_at=deleted_at,
        expires_at=expires_at,
        retention_days=retention_days,
    )
    if history is None:
        return None
    db.add(history)
    return history
