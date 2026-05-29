"""
tests/test_phase11_dept_fk.py - Phase 11 T-1104 User.department_id FK dual-track tests.

覆盖范围:
  - Model 层:department_id nullable / set / ON DELETE SET NULL
  - Backfill 层:字符串部门映射 / unmapped 保留 NULL / 空字符串保留 NULL
  - Resolver 层:FK 优先 / 字符串 fallback / 空串 fallback / name -> id
  - Service 层:get_department_with_members 双轨 OR 反查
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.department import Department
from app.models.user import User, UserRole
from app.services._department_resolver import resolve_department_id_by_name, resolve_user_department_name
from app.services.department_service import get_department_with_members
from tests._db_url import derive_test_database_url

TENANT_ID = "default"
OTHER_TENANT_ID = "phase11_other"
TEST_DATABASE_URL = derive_test_database_url(settings.database_url)
pytestmark = pytest.mark.asyncio


async def _cleanup_phase11_test_data(db: AsyncSession) -> None:
    phase11_user_ids = select(User.id).where(User.wechat_userid.like("phase11_%"))
    await db.execute(delete(Department).where(Department.name.like("phase11_%")))
    await db.execute(delete(User).where(User.id.in_(phase11_user_ids)))
    await db.flush()


async def _phase11_make_department(
    db: AsyncSession,
    name: str = "phase11_技术部",
    *,
    tenant_id: str = TENANT_ID,
    manager_id: uuid.UUID | None = None,
) -> Department:
    dept = Department(
        id=uuid.uuid4(),
        name=name,
        manager_id=manager_id,
        tenant_id=tenant_id,
    )
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return dept


async def _phase11_make_user(
    db: AsyncSession,
    *,
    name: str = "phase11_user",
    department: str = "",
    department_id: uuid.UUID | None = None,
    role: UserRole = UserRole.employee,
    is_active: bool = True,
    tenant_id: str = TENANT_ID,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"phase11_{uuid.uuid4().hex[:12]}",
        name=name,
        department=department,
        department_id=department_id,
        job_title="工程师",
        role=role,
        is_active=is_active,
        tenant_id=tenant_id,
        must_change_password=False,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def _phase11_run_backfill(db: AsyncSession) -> None:
    await db.execute(
        text(
            "UPDATE users SET department_id = d.id "
            "FROM departments d "
            "WHERE users.department = d.name AND users.department != ''"
        )
    )
    await db.flush()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        await _cleanup_phase11_test_data(session)
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
            await _cleanup_phase11_test_data(session)
            await session.commit()
    await engine.dispose()


async def test_user_department_id_nullable(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)

    user = await _phase11_make_user(db_session, department="phase11_技术部", department_id=None)

    assert user.department_id is None


async def test_user_department_id_set_to_department(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_model_set")

    user = await _phase11_make_user(db_session, department=dept.name, department_id=dept.id)
    await db_session.refresh(user)

    assert user.department_id == dept.id


async def test_user_department_id_fk_set_null_on_department_delete(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_model_delete")
    user = await _phase11_make_user(db_session, department=dept.name, department_id=dept.id)

    await db_session.delete(dept)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.department_id is None


async def test_backfill_maps_existing_department_string(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_backfill_map")
    user = await _phase11_make_user(db_session, department=dept.name, department_id=None)

    await _phase11_run_backfill(db_session)
    await db_session.refresh(user)

    assert user.department_id == dept.id


async def test_backfill_leaves_unmapped_department_string(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    user = await _phase11_make_user(db_session, department="phase11_backfill_unmapped", department_id=None)

    await _phase11_run_backfill(db_session)
    await db_session.refresh(user)

    assert user.department_id is None
    assert user.department == "phase11_backfill_unmapped"


async def test_backfill_leaves_empty_department_string(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    user = await _phase11_make_user(db_session, department="", department_id=None)

    await _phase11_run_backfill(db_session)
    await db_session.refresh(user)

    assert user.department_id is None
    assert user.department == ""


async def test_resolve_returns_department_name_via_fk(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_resolver_fk")
    user = await _phase11_make_user(db_session, department="phase11_old_name", department_id=dept.id)

    assert await resolve_user_department_name(db_session, user) == dept.name


async def test_resolve_fallback_to_string_when_id_null(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    user = await _phase11_make_user(db_session, department="phase11_resolver_string", department_id=None)

    assert await resolve_user_department_name(db_session, user) == "phase11_resolver_string"


async def test_resolve_fallback_to_empty_when_both_null(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    user = await _phase11_make_user(db_session, department="", department_id=None)

    assert await resolve_user_department_name(db_session, user) == ""


async def test_resolve_department_id_by_name_returns_uuid(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_resolver_lookup")

    assert await resolve_department_id_by_name(db_session, dept.name) == dept.id
    assert await resolve_department_id_by_name(db_session, "phase11_resolver_missing") is None
    assert await resolve_department_id_by_name(db_session, "") is None


async def test_get_department_with_members_returns_fk_users(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_service_fk")
    user = await _phase11_make_user(
        db_session,
        name="phase11_service_fk_user",
        department="phase11_legacy_drift",
        department_id=dept.id,
    )

    result = await get_department_with_members(db_session, dept.id, tenant_id=TENANT_ID)

    assert {member.id for member in result.members} == {user.id}


async def test_get_department_with_members_returns_fallback_users(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_service_fallback")
    user = await _phase11_make_user(db_session, name="phase11_service_fallback_user", department=dept.name)

    result = await get_department_with_members(db_session, dept.id, tenant_id=TENANT_ID)

    assert {member.id for member in result.members} == {user.id}


async def test_get_department_with_members_excludes_inactive(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_service_active")
    active_user = await _phase11_make_user(
        db_session,
        name="phase11_service_active_user",
        department=dept.name,
        department_id=dept.id,
    )
    await _phase11_make_user(
        db_session,
        name="phase11_service_inactive_user",
        department=dept.name,
        department_id=dept.id,
        is_active=False,
    )

    result = await get_department_with_members(db_session, dept.id, tenant_id=TENANT_ID)

    assert {member.id for member in result.members} == {active_user.id}


async def test_get_department_with_members_excludes_other_tenant(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_service_tenant")
    await _phase11_make_user(
        db_session,
        name="phase11_other_tenant",
        department=dept.name,
        department_id=dept.id,
        tenant_id=OTHER_TENANT_ID,
    )

    result = await get_department_with_members(db_session, dept.id, tenant_id=TENANT_ID)

    assert result.members == []


async def test_get_department_with_members_returns_empty_when_no_match(db_session: AsyncSession) -> None:
    await _cleanup_phase11_test_data(db_session)
    dept = await _phase11_make_department(db_session, "phase11_service_empty")

    result = await get_department_with_members(db_session, dept.id, tenant_id=TENANT_ID)

    assert result.members == []
