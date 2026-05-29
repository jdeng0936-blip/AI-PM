"""
tests/test_phase11_followups.py - Phase 11 T-1106 project followup closure tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.middleware.rbac import create_access_token
from app.models.project import Project, ProjectHealthStatus, ProjectStatus, ProjectTrack
from app.models.project_followup import ProjectFollowUp
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage
from app.models.sprint import Sprint
from app.models.user import User, UserRole
from app.services.health_engine import refresh_project_health
from tests._db_url import derive_test_database_url

TENANT_ID = "default"
OTHER_TENANT_ID = "phase11_followup_other"
TEST_DATABASE_URL = derive_test_database_url(settings.database_url)
pytestmark = pytest.mark.asyncio


async def _cleanup_phase11_followup_test_data(db_session: AsyncSession) -> None:
    phase11_followup_user_ids = select(User.id).where(User.wechat_userid.like("phase11_followup_%"))
    phase11_followup_project_ids = select(Project.id).where(
        or_(
            Project.code.like("phase11_followu%"),
            Project.name.like("phase11_followup_%"),
        )
    )

    await db_session.execute(
        delete(ProjectFollowUp).where(ProjectFollowUp.project_id.in_(phase11_followup_project_ids))
    )
    await db_session.execute(
        delete(ProjectMember).where(
            or_(
                ProjectMember.user_id.in_(phase11_followup_user_ids),
                ProjectMember.project_id.in_(phase11_followup_project_ids),
            )
        )
    )
    await db_session.execute(delete(Sprint).where(Sprint.project_id.in_(phase11_followup_project_ids)))
    await db_session.execute(delete(ProjectStage).where(ProjectStage.project_id.in_(phase11_followup_project_ids)))
    await db_session.execute(delete(Project).where(Project.id.in_(phase11_followup_project_ids)))
    await db_session.execute(delete(User).where(User.id.in_(phase11_followup_user_ids)))
    await db_session.flush()


def _phase11_followup_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _phase11_followup_make_user(
    db_session: AsyncSession,
    *,
    wechat_userid: str,
    name: str = "phase11 followup user",
    role: UserRole = UserRole.employee,
    department: str = "",
    tenant_id: str = TENANT_ID,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=wechat_userid,
        name=name,
        department=department,
        job_title="工程师",
        role=role,
        is_active=True,
        tenant_id=tenant_id,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def _phase11_followup_make_project(
    db_session: AsyncSession,
    *,
    creator: User,
    code: str = "phase11_followu1",
    name: str = "phase11_followup_project",
    is_temporary: bool = True,
    status: ProjectStatus = ProjectStatus.active,
    created_at: datetime | None = None,
    tenant_id: str = TENANT_ID,
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        code=code,
        description="phase11 followup test project",
        track=ProjectTrack.support if is_temporary else ProjectTrack.dual,
        status=status,
        is_temporary=is_temporary,
        health_status=ProjectHealthStatus.green,
        health_score=100,
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    if created_at is not None:
        project.created_at = created_at
    db_session.add(project)
    await db_session.flush()
    await db_session.refresh(project)
    return project


async def _phase11_followup_make_member(
    db_session: AsyncSession,
    *,
    project: Project,
    user: User,
    creator: User,
    tenant_id: str = TENANT_ID,
) -> ProjectMember:
    member = ProjectMember(
        project_id=project.id,
        user_id=user.id,
        track="both",
        role_in_project="协作成员",
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    db_session.add(member)
    await db_session.flush()
    await db_session.refresh(member)
    return member


async def _phase11_followup_make_followup(
    db_session: AsyncSession,
    *,
    project: Project,
    creator: User,
    content: str = "phase11 followup content",
    created_at: datetime | None = None,
    tenant_id: str = TENANT_ID,
) -> ProjectFollowUp:
    followup = ProjectFollowUp(
        id=uuid.uuid4(),
        project_id=project.id,
        content=content,
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    if created_at is not None:
        followup.created_at = created_at
    db_session.add(followup)
    await db_session.flush()
    await db_session.refresh(followup)
    return followup


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS resolution_summary VARCHAR(2048)"))
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        await _cleanup_phase11_followup_test_data(session)
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
            await _cleanup_phase11_followup_test_data(session)
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


async def test_project_followup_basic_create_persists(db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_a",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)

    followup = await _phase11_followup_make_followup(
        db_session,
        project=project,
        creator=manager,
        content="已联系采购确认样件到货时间",
    )
    await db_session.commit()

    saved = await db_session.scalar(select(ProjectFollowUp).where(ProjectFollowUp.id == followup.id))
    assert saved is not None
    assert saved.project_id == project.id
    assert saved.content == "已联系采购确认样件到货时间"
    assert saved.created_by == manager.id


async def test_project_followup_cascade_delete_with_project(db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_b",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    followup = await _phase11_followup_make_followup(db_session, project=project, creator=manager)
    await db_session.commit()

    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()

    count = await db_session.scalar(
        select(func.count()).select_from(ProjectFollowUp).where(ProjectFollowUp.id == followup.id)
    )
    assert int(count or 0) == 0


async def test_project_resolution_summary_field_persists(db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_c",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)

    project.resolution_summary = "已完成客户现场支持并回收问题清单"
    await db_session.commit()
    await db_session.refresh(project)

    assert project.resolution_summary == "已完成客户现场支持并回收问题清单"


async def test_post_followup_returns_201_with_basic_payload(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_d",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/projects/{project.id}/followups",
        headers=_phase11_followup_headers(create_access_token(str(manager.id), manager.role.value)),
        json={"content": "同步现场负责人,等待设备复测"},
    )

    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["id"])
    assert body["project_id"] == str(project.id)
    assert body["content"] == "同步现场负责人,等待设备复测"
    assert body["created_at"]


async def test_post_followup_employee_can_create_for_own_project(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_e",
        role=UserRole.manager,
    )
    employee = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_emp_e",
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    await _phase11_followup_make_member(db_session, project=project, user=employee, creator=manager)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/projects/{project.id}/followups",
        headers=_phase11_followup_headers(create_access_token(str(employee.id), employee.role.value)),
        json={"content": "员工补充了客户回访结论"},
    )

    assert response.status_code == 201
    assert response.json()["content"] == "员工补充了客户回访结论"


async def test_post_followup_employee_cannot_create_for_other_project(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_f",
        role=UserRole.manager,
    )
    employee = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_emp_f",
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/projects/{project.id}/followups",
        headers=_phase11_followup_headers(create_access_token(str(employee.id), employee.role.value)),
        json={"content": "非成员尝试追加"},
    )

    assert response.status_code == 404


async def test_get_followups_orders_by_created_desc(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_g",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    new_time = datetime.now(timezone.utc) - timedelta(hours=1)
    await _phase11_followup_make_followup(
        db_session,
        project=project,
        creator=manager,
        content="较早进展",
        created_at=old_time,
    )
    await _phase11_followup_make_followup(
        db_session,
        project=project,
        creator=manager,
        content="最新进展",
        created_at=new_time,
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/projects/{project.id}/followups",
        headers=_phase11_followup_headers(create_access_token(str(manager.id), manager.role.value)),
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["content"] for item in body] == ["最新进展", "较早进展"]


async def test_get_followups_respects_limit_param(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_h",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    for index in range(5):
        await _phase11_followup_make_followup(
            db_session,
            project=project,
            creator=manager,
            content=f"进展 {index}",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=index),
        )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/projects/{project.id}/followups?limit=3",
        headers=_phase11_followup_headers(create_access_token(str(manager.id), manager.role.value)),
    )

    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_patch_temporary_project_completed_without_resolution_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_i",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/projects/{project.id}",
        headers=_phase11_followup_headers(create_access_token(str(manager.id), manager.role.value)),
        json={"status": "completed"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "临时工单完工必须填写处理结果 resolution_summary"


async def test_patch_temporary_project_completed_with_resolution_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_j",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/projects/{project.id}",
        headers=_phase11_followup_headers(create_access_token(str(manager.id), manager.role.value)),
        json={"status": "completed", "resolution_summary": "已完成定位,交付处理报告"},
    )
    await db_session.refresh(project)

    assert response.status_code == 200
    assert project.status == ProjectStatus.completed
    assert project.resolution_summary == "已完成定位,交付处理报告"


async def test_patch_main_project_completed_without_resolution_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_k",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(
        db_session,
        creator=manager,
        code="phase11_followu2",
        name="phase11_followup_main_project",
        is_temporary=False,
    )
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/projects/{project.id}",
        headers=_phase11_followup_headers(create_access_token(str(manager.id), manager.role.value)),
        json={"status": "completed"},
    )
    await db_session.refresh(project)

    assert response.status_code == 200
    assert project.status == ProjectStatus.completed
    assert project.resolution_summary is None


async def test_temporary_project_no_followup_uses_created_at_baseline(db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_l",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(
        db_session,
        creator=manager,
        created_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    await db_session.commit()

    await refresh_project_health(db_session, project.id)
    await db_session.refresh(project)

    assert project.health_status == ProjectHealthStatus.green
    assert project.health_score == 100


async def test_temporary_project_stale_7_to_14_days_yellow(db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_m",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    await _phase11_followup_make_followup(
        db_session,
        project=project,
        creator=manager,
        created_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    await db_session.commit()

    await refresh_project_health(db_session, project.id)
    await db_session.refresh(project)

    assert project.health_status == ProjectHealthStatus.yellow
    assert project.health_score == 60


async def test_temporary_project_stale_over_14_days_red(db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_n",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(db_session, creator=manager)
    await _phase11_followup_make_followup(
        db_session,
        project=project,
        creator=manager,
        created_at=datetime.now(timezone.utc) - timedelta(days=15),
    )
    await db_session.commit()

    await refresh_project_health(db_session, project.id)
    await db_session.refresh(project)

    assert project.health_status == ProjectHealthStatus.red
    assert project.health_score == 30


async def test_temporary_project_completed_always_green(db_session: AsyncSession) -> None:
    await _cleanup_phase11_followup_test_data(db_session)
    manager = await _phase11_followup_make_user(
        db_session,
        wechat_userid="phase11_followup_mgr_o",
        role=UserRole.manager,
    )
    project = await _phase11_followup_make_project(
        db_session,
        creator=manager,
        status=ProjectStatus.completed,
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    await _phase11_followup_make_followup(
        db_session,
        project=project,
        creator=manager,
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    await db_session.commit()

    await refresh_project_health(db_session, project.id)
    await db_session.refresh(project)

    assert project.health_status == ProjectHealthStatus.green
    assert project.health_score == 100
