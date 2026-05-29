"""
tests/test_phase11_project_members.py - Phase 11 T-1105 project create member initialization tests.
"""

from __future__ import annotations

import uuid
from importlib import import_module
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_db
from app.middleware.rbac import create_access_token
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage
from app.models.sprint import Sprint
from app.models.user import User, UserRole
from app.schemas.project import ProjectCreate
from tests._db_url import derive_test_database_url

TENANT_ID = "default"
OTHER_TENANT_ID = "phase11_picker_other"
TEST_DATABASE_URL = derive_test_database_url(settings.database_url)
pytestmark = pytest.mark.asyncio


async def _cleanup_phase11_picker_test_data(db_session: AsyncSession) -> None:
    phase11_picker_user_ids = select(User.id).where(User.wechat_userid.like("phase11_picker_%"))
    phase11_picker_project_ids = select(Project.id).where(Project.code.like("phase11_picker_%"))

    await db_session.execute(
        delete(ProjectMember).where(
            or_(
                ProjectMember.user_id.in_(phase11_picker_user_ids),
                ProjectMember.project_id.in_(phase11_picker_project_ids),
            )
        )
    )
    await db_session.execute(delete(Sprint).where(Sprint.project_id.in_(phase11_picker_project_ids)))
    await db_session.execute(delete(ProjectStage).where(ProjectStage.project_id.in_(phase11_picker_project_ids)))
    await db_session.execute(delete(Project).where(Project.id.in_(phase11_picker_project_ids)))
    await db_session.execute(delete(User).where(User.id.in_(phase11_picker_user_ids)))
    await db_session.flush()


def _phase11_picker_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _phase11_picker_make_user(
    db_session: AsyncSession,
    *,
    wechat_userid: str,
    name: str = "测试用户",
    role: UserRole = UserRole.employee,
    department: str = "",
    is_active: bool = True,
    tenant_id: str = TENANT_ID,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=wechat_userid,
        name=name,
        department=department,
        job_title="工程师",
        role=role,
        is_active=is_active,
        tenant_id=tenant_id,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def _phase11_picker_project_count(db_session: AsyncSession, code: str) -> int:
    count = await db_session.scalar(select(func.count()).select_from(Project).where(Project.code == code))
    return int(count or 0)


async def _phase11_picker_member_count(db_session: AsyncSession) -> int:
    phase11_picker_user_ids = select(User.id).where(User.wechat_userid.like("phase11_picker_%"))
    phase11_picker_project_ids = select(Project.id).where(Project.code.like("phase11_picker_%"))
    count = await db_session.scalar(
        select(func.count())
        .select_from(ProjectMember)
        .where(
            or_(
                ProjectMember.user_id.in_(phase11_picker_user_ids),
                ProjectMember.project_id.in_(phase11_picker_project_ids),
            )
        )
    )
    return int(count or 0)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        await _cleanup_phase11_picker_test_data(session)
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
            await _cleanup_phase11_picker_test_data(session)
            await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app = import_module("app.main").app
    test_app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=cast(Any, test_app))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    test_app.dependency_overrides.clear()


async def test_project_create_accepts_members_field(db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    user_id = uuid.uuid4()

    payload = ProjectCreate(
        name="phase11 picker schema",
        members=[{"user_id": user_id, "track": "both", "role_in_project": "PM"}],
    )

    assert payload.members is not None
    assert payload.members[0].user_id == user_id
    assert payload.members[0].track == "both"
    assert payload.members[0].role_in_project == "PM"


async def test_project_create_accepts_none_members(db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)

    assert ProjectCreate(name="phase11 picker no members").members is None
    assert ProjectCreate(name="phase11 picker none members", members=None).members is None


async def test_project_member_init_max_length_50_enforced(db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    members = [{"user_id": uuid.uuid4(), "track": "both"} for _ in range(51)]

    with pytest.raises(ValidationError):
        ProjectCreate(name="phase11 picker too many members", members=members)


async def test_create_project_with_3_members_success(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    manager = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_mgr_a",
        name="phase11 picker manager a",
        role=UserRole.manager,
    )
    members = [
        await _phase11_picker_make_user(
            db_session,
            wechat_userid=f"phase11_picker_user_a{i}",
            name=f"phase11 picker user a{i}",
            department="phase11 picker dept",
        )
        for i in range(3)
    ]
    await db_session.commit()

    response = await client.post(
        "/api/v1/projects/",
        headers=_phase11_picker_headers(create_access_token(str(manager.id), manager.role.value)),
        json={
            "name": "phase11 picker main project",
            "code": "phase11_picker_a",
            "track": "dual",
            "members": [
                {"user_id": str(members[0].id), "track": "both", "role_in_project": "PM"},
                {"user_id": str(members[1].id), "track": "hardware", "role_in_project": "HW"},
                {"user_id": str(members[2].id), "track": "software", "role_in_project": "SW"},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["members_added"] == 3
    project_id = uuid.UUID(body["project_id"])
    stage_count = await db_session.scalar(
        select(func.count()).select_from(ProjectStage).where(ProjectStage.project_id == project_id)
    )
    member_rows = (
        (
            await db_session.execute(
                select(ProjectMember)
                .where(ProjectMember.project_id == project_id)
                .order_by(ProjectMember.role_in_project)
            )
        )
        .scalars()
        .all()
    )
    assert stage_count == 5
    assert len(member_rows) == 3
    assert {m.user_id for m in member_rows} == {m.id for m in members}
    assert {m.tenant_id for m in member_rows} == {TENANT_ID}
    assert {m.created_by for m in member_rows} == {manager.id}


async def test_create_project_with_empty_members_zero_member_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    manager = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_mgr_b",
        name="phase11 picker manager b",
        role=UserRole.manager,
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/projects/",
        headers=_phase11_picker_headers(create_access_token(str(manager.id), manager.role.value)),
        json={
            "name": "phase11 picker empty project",
            "code": "phase11_picker_b",
            "track": "software",
            "members": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["members_added"] == 0
    project_id = uuid.UUID(body["project_id"])
    member_count = await db_session.scalar(
        select(func.count()).select_from(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    assert member_count == 0


async def test_create_project_with_duplicate_user_ids_400(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    manager = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_mgr_c",
        name="phase11 picker manager c",
        role=UserRole.manager,
    )
    user = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_user_c",
        name="phase11 picker user c",
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/projects/",
        headers=_phase11_picker_headers(create_access_token(str(manager.id), manager.role.value)),
        json={
            "name": "phase11 picker duplicate project",
            "code": "phase11_picker_c",
            "members": [
                {"user_id": str(user.id), "track": "both"},
                {"user_id": str(user.id), "track": "software"},
            ],
        },
    )

    assert response.status_code == 400
    assert "成员列表中重复的 user_id" in response.json()["detail"]
    assert await _phase11_picker_project_count(db_session, "phase11_picker_c") == 0


async def test_create_project_with_missing_user_id_400_rollback(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    manager = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_mgr_d",
        name="phase11 picker manager d",
        role=UserRole.manager,
    )
    missing_user_id = uuid.uuid4()
    await db_session.commit()

    response = await client.post(
        "/api/v1/projects/",
        headers=_phase11_picker_headers(create_access_token(str(manager.id), manager.role.value)),
        json={
            "name": "phase11 picker missing project",
            "code": "phase11_picker_d",
            "members": [{"user_id": str(missing_user_id), "track": "both"}],
        },
    )

    assert response.status_code == 400
    assert "以下 user_id 不存在" in response.json()["detail"]
    assert await _phase11_picker_project_count(db_session, "phase11_picker_d") == 0
    assert await _phase11_picker_member_count(db_session) == 0


async def test_create_temporary_project_with_2_members_success(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    manager = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_mgr_e",
        name="phase11 picker manager e",
        role=UserRole.manager,
    )
    user_a = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_user_e1",
        name="phase11 picker user e1",
    )
    user_b = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_user_e2",
        name="phase11 picker user e2",
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/projects/",
        headers=_phase11_picker_headers(create_access_token(str(manager.id), manager.role.value)),
        json={
            "name": "phase11 picker temporary project",
            "code": "phase11_picker_e",
            "track": "support",
            "is_temporary": True,
            "members": [
                {"user_id": str(user_a.id), "track": "both", "role_in_project": "owner"},
                {"user_id": str(user_b.id), "track": "software", "role_in_project": "support"},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_temporary"] is True
    assert body["members_added"] == 2
    project_id = uuid.UUID(body["project_id"])
    project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    sprint_count = await db_session.scalar(
        select(func.count()).select_from(Sprint).where(Sprint.project_id == project_id, Sprint.sprint_number == 0)
    )
    member_count = await db_session.scalar(
        select(func.count()).select_from(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    assert project.is_temporary is True
    assert sprint_count == 1
    assert member_count == 2


async def test_user_picker_admin_lists_users(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    admin = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_admin_i",
        name="phase11 picker admin i",
        role=UserRole.admin,
    )
    active_user = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_active_i",
        name="phase11 picker active i",
        department="phase11 picker dept",
    )
    inactive_user = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_inactive_i",
        name="phase11 picker inactive i",
        is_active=False,
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/users/picker",
        headers=_phase11_picker_headers(create_access_token(str(admin.id), admin.role.value)),
    )

    assert response.status_code == 200
    items = response.json()
    ids = {item["id"] for item in items}
    assert str(active_user.id) in ids
    assert str(inactive_user.id) not in ids
    active_item = next(item for item in items if item["id"] == str(active_user.id))
    assert active_item == {
        "id": str(active_user.id),
        "name": active_user.name,
        "department": active_user.department,
        "role": active_user.role.value,
        "is_active": True,
    }


async def test_user_picker_manager_lists_users(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    manager = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_mgr_j",
        name="phase11 picker manager j",
        role=UserRole.manager,
    )
    employee = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_user_j",
        name="phase11 picker user j",
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/users/picker",
        headers=_phase11_picker_headers(create_access_token(str(manager.id), manager.role.value)),
    )

    assert response.status_code == 200
    assert str(employee.id) in {item["id"] for item in response.json()}


async def test_user_picker_employee_403(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    employee = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_employee_k",
        name="phase11 picker employee k",
        role=UserRole.employee,
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/users/picker",
        headers=_phase11_picker_headers(create_access_token(str(employee.id), employee.role.value)),
    )

    assert response.status_code == 403


async def test_create_project_members_cross_tenant_user_id_blocked(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase11_picker_test_data(db_session)
    manager = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_mgr_l",
        name="phase11 picker manager l",
        role=UserRole.manager,
    )
    other_tenant_user = await _phase11_picker_make_user(
        db_session,
        wechat_userid="phase11_picker_other_l",
        name="phase11 picker other tenant l",
        tenant_id=OTHER_TENANT_ID,
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/projects/",
        headers=_phase11_picker_headers(create_access_token(str(manager.id), manager.role.value)),
        json={
            "name": "phase11 picker tenant project",
            "code": "phase11_picker_f",
            "members": [{"user_id": str(other_tenant_user.id), "track": "both"}],
        },
    )

    assert response.status_code == 400
    assert "以下 user_id 不存在" in response.json()["detail"]
    assert await _phase11_picker_project_count(db_session, "phase11_picker_f") == 0
