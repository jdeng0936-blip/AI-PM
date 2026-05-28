from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.middleware.rbac import create_access_token
from app.models.daily_report import DailyReport
from app.models.deletion_history import DeletionHistory
from app.models.user import User, UserRole
from app.routers.me_deletions import _can_restore_batch

TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")


def _user(role: UserRole = UserRole.employee) -> User:
    return User(
        id=uuid.uuid4(),
        wechat_userid=f"me_del_{uuid.uuid4().hex[:10]}",
        name="删除测试员",
        department="测试部",
        job_title="工程师",
        role=role,
        is_active=True,
        must_change_password=False,
    )


def _history_for(actor: User) -> DeletionHistory:
    now = datetime.now(timezone.utc)
    return DeletionHistory(
        actor_id=actor.id,
        table_name="daily_reports",
        record_ids=[str(uuid.uuid4())],
        deleted_at=now,
        expires_at=now + timedelta(days=30),
    )


def test_can_restore_batch_boundaries():
    owner = _user()
    other = _user()

    active = _history_for(owner)
    assert _can_restore_batch(active, owner) is True
    assert _can_restore_batch(active, other) is False

    restored = _history_for(owner)
    restored.restored_at = datetime.now(timezone.utc)
    assert _can_restore_batch(restored, owner) is False

    hard_deleted = _history_for(owner)
    hard_deleted.hard_deleted_at = datetime.now(timezone.utc)
    assert _can_restore_batch(hard_deleted, owner) is False


@pytest_asyncio.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncSession], None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:

        async def _get_test_db():
            yield session

        app.dependency_overrides[get_db] = _get_test_db
        transport = ASGITransport(app=cast(Any, app))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, session
        app.dependency_overrides.clear()

    await engine.dispose()


@pytest.mark.asyncio
async def test_employee_can_restore_own_deleted_report_and_other_employee_cannot(client_and_db):
    client, db = client_and_db
    employee_a = _user()
    employee_b = _user()
    db.add_all([employee_a, employee_b])
    await db.commit()
    await db.refresh(employee_a)
    await db.refresh(employee_b)

    report = DailyReport(
        user_id=employee_a.id,
        report_date=date.today(),
        raw_input_text="今天完成了删除恢复联调。",
        parsed_content={"tasks": "删除恢复联调"},
        pass_check=True,
        ai_score=90,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    headers_a = {"Authorization": f"Bearer {create_access_token(str(employee_a.id), employee_a.role.value)}"}
    headers_b = {"Authorization": f"Bearer {create_access_token(str(employee_b.id), employee_b.role.value)}"}

    delete_res = await client.request(
        "DELETE",
        "/api/v1/reports/batch",
        json={"ids": [str(report.id)]},
        headers=headers_a,
    )
    assert delete_res.status_code == 200
    assert delete_res.json()["deleted_count"] == 1

    list_res = await client.get("/api/v1/me/deletions", headers=headers_a)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) >= 1
    batch = next(item for item in items if item["table_name"] == "daily_reports")
    assert batch["record_ids"] == 1
    assert batch["record_count"] == 1
    assert batch["days_remaining"] is not None

    forbidden_res = await client.patch(f"/api/v1/me/deletions/{batch['id']}/restore", headers=headers_b)
    assert forbidden_res.status_code == 403

    restore_res = await client.patch(f"/api/v1/me/deletions/{batch['id']}/restore", headers=headers_a)
    assert restore_res.status_code == 200
    assert restore_res.json()["restored_count"] == 1

    await db.refresh(report)
    assert report.deleted_at is None
    history = await db.get(DeletionHistory, uuid.UUID(batch["id"]))
    assert history is not None
    assert history.restored_at is not None
