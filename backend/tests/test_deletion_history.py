from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.deletion_history import (
    SOFT_DELETE_RETENTION_DAYS,
    build_deletion_history,
    mark_soft_delete_restored,
    normalize_record_ids,
)


def test_normalize_record_ids_deduplicates_and_canonicalizes_uuid_strings():
    item_id = uuid.uuid4()

    assert normalize_record_ids([str(item_id).upper(), item_id]) == [str(item_id)]


def test_build_deletion_history_sets_batch_expiry():
    actor_id = uuid.uuid4()
    item_id = uuid.uuid4()
    deleted_at = datetime(2026, 5, 26, 13, 0, tzinfo=timezone.utc)

    history = build_deletion_history(
        actor_id=actor_id,
        table_name="daily_reports",
        record_ids=[item_id],
        deleted_at=deleted_at,
    )

    assert history is not None
    assert history.actor_id == actor_id
    assert history.created_by == actor_id
    assert history.table_name == "daily_reports"
    assert history.record_ids == [str(item_id)]
    assert history.deleted_at == deleted_at
    assert (history.expires_at - deleted_at).days == SOFT_DELETE_RETENTION_DAYS


def test_build_deletion_history_returns_none_for_empty_hits():
    history = build_deletion_history(
        actor_id=uuid.uuid4(),
        table_name="risk_alerts",
        record_ids=[],
    )

    assert history is None


def test_build_deletion_history_rejects_untracked_tables():
    with pytest.raises(ValueError, match="未纳入 deletion_history 治理"):
        build_deletion_history(
            actor_id=uuid.uuid4(),
            table_name="project_members",
            record_ids=[uuid.uuid4()],
        )


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarResult(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _ExecuteResult(self._rows)


@pytest.mark.asyncio
async def test_mark_soft_delete_restored_only_marks_fully_restored_batches():
    actor_id = uuid.uuid4()
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    third_id = uuid.uuid4()
    deleted_at = datetime(2026, 5, 26, 13, 0, tzinfo=timezone.utc)
    full_batch = build_deletion_history(
        actor_id=actor_id,
        table_name="daily_reports",
        record_ids=[first_id, second_id],
        deleted_at=deleted_at,
    )
    partial_batch = build_deletion_history(
        actor_id=actor_id,
        table_name="daily_reports",
        record_ids=[third_id, uuid.uuid4()],
        deleted_at=deleted_at,
    )
    assert full_batch is not None
    assert partial_batch is not None

    restored_by = uuid.uuid4()
    marked = await mark_soft_delete_restored(
        cast(AsyncSession, _FakeSession([full_batch, partial_batch])),
        table_name="daily_reports",
        record_ids=[first_id, second_id, third_id],
        restored_by=restored_by,
        restored_at=deleted_at,
    )

    assert marked == 1
    assert full_batch.restored_at == deleted_at
    assert full_batch.restored_by == restored_by
    assert partial_batch.restored_at is None
