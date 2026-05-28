"""
tests/test_phase10_dept_group.py — Phase 10 部门 + 项目分组聚合后端测试

覆盖范围:
  - Model 层: ProjectMember partial UNIQUE (project_id, user_id) WHERE left_at IS NULL
             + Department.name UNIQUE
  - Service 层: department_service.get_department_with_members (反查 + 空)
              + admin_reports_service.group_reports_by_department / by_project
              + _validate_date_range
  - Router 层: /api/v1/admin/departments 5 端点 (200 / 403 / 400 / 409)
             + /api/v1/admin/reports 1 端点 (200 / 403 / 422 / 400)
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from importlib import import_module
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_db
from app.middleware.rbac import create_access_token
from app.models.daily_report import DailyReport
from app.models.department import Department
from app.models.project import Project
from app.models.project_member import MemberTrack, ProjectMember
from app.models.user import User, UserRole
from app.services.admin_reports_service import (
    _validate_date_range,
    group_reports_by_department,
    group_reports_by_project,
)
from app.services.department_service import get_department_with_members
from tests._db_url import derive_test_database_url

TENANT_ID = "default"
TEST_DATABASE_URL = derive_test_database_url(settings.database_url)
pytestmark = pytest.mark.asyncio


async def _cleanup_phase10_test_data(db: AsyncSession) -> None:
    """测试前清理本测试创建的 phase10_* 用户及连锁 ORM 行。"""
    phase10_user_ids = select(User.id).where(User.wechat_userid.like("phase10_%"))
    phase10_project_ids = select(Project.id).where(Project.code.like("P10%"))

    await db.execute(
        delete(DailyReport).where(
            or_(
                DailyReport.user_id.in_(phase10_user_ids),
                DailyReport.project_id.in_(phase10_project_ids),
                DailyReport.raw_input_text.like("phase10%"),
            )
        )
    )
    await db.execute(
        delete(ProjectMember).where(
            or_(
                ProjectMember.user_id.in_(phase10_user_ids),
                ProjectMember.project_id.in_(phase10_project_ids),
            )
        )
    )
    await db.execute(delete(Department).where(Department.name.like("Phase10%")))
    await db.execute(delete(Project).where(Project.id.in_(phase10_project_ids)))
    await db.execute(delete(User).where(User.id.in_(phase10_user_ids)))
    await db.flush()


async def _make_user(
    db: AsyncSession,
    role: UserRole,
    name: str = "Phase10 用户",
    department: str = "Phase10 技术部",
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"phase10_{uuid.uuid4().hex[:12]}",
        name=name,
        department=department,
        job_title="工程师",
        role=role,
        is_active=is_active,
        tenant_id=TENANT_ID,
        must_change_password=False,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


async def _make_department(db: AsyncSession, name: str, manager_id: uuid.UUID | None = None) -> Department:
    dept = Department(id=uuid.uuid4(), name=name, manager_id=manager_id, tenant_id=TENANT_ID)
    db.add(dept)
    await db.flush()
    await db.refresh(dept)
    return dept


async def _make_project(db: AsyncSession, name: str = "Phase10 项目") -> Project:
    project = Project(id=uuid.uuid4(), name=name, code=f"P10{uuid.uuid4().hex[:10]}", tenant_id=TENANT_ID)
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


async def _make_daily_report(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    report_date: date,
    ai_score: float,
    pass_check: bool,
) -> DailyReport:
    report = DailyReport(
        id=uuid.uuid4(),
        user_id=user_id,
        project_id=project_id,
        report_date=report_date,
        raw_input_text="phase10 test content",
        parsed_content={"tasks": "phase10 test"},
        ai_score=int(ai_score),
        pass_check=pass_check,
        tenant_id=TENANT_ID,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """本地 fixture 避免路由服务 commit 与 conftest 嵌套事务冲突。"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        await _cleanup_phase10_test_data(session)
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
            await _cleanup_phase10_test_data(session)
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


async def test_project_member_unique_active_blocks_duplicate(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    user = await _make_user(db_session, UserRole.employee, name="Phase10 PM User")
    project = await _make_project(db_session)

    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            track=MemberTrack.software,
            tenant_id=TENANT_ID,
        )
    )
    await db_session.flush()

    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            track=MemberTrack.hardware,
            tenant_id=TENANT_ID,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_project_member_unique_active_allows_after_left(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    user = await _make_user(db_session, UserRole.employee, name="Phase10 PM Left User")
    project = await _make_project(db_session)

    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            track=MemberTrack.software,
            left_at=date.today() - timedelta(days=1),
            tenant_id=TENANT_ID,
        )
    )
    await db_session.flush()
    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            track=MemberTrack.hardware,
            tenant_id=TENANT_ID,
        )
    )
    await db_session.flush()

    rows = (
        (
            await db_session.execute(
                select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2


async def test_department_unique_name_blocks_duplicate(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    await _make_department(db_session, "Phase10 唯一部门")
    db_session.add(Department(id=uuid.uuid4(), name="Phase10 唯一部门", tenant_id=TENANT_ID))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_dept_service_get_with_members_returns_active_users(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    dept = await _make_department(db_session, "Phase10 技术部")
    active_names = {"Phase10 Active A", "Phase10 Active B", "Phase10 Active C"}
    for name in active_names:
        await _make_user(db_session, UserRole.employee, name=name, department=dept.name)
    await _make_user(db_session, UserRole.employee, name="Phase10 Inactive", department=dept.name, is_active=False)

    result = await get_department_with_members(db_session, dept.id, tenant_id=TENANT_ID)

    assert {member.name for member in result.members} == active_names
    assert all(member.department == dept.name for member in result.members)


async def test_dept_service_get_with_members_empty_returns_empty_list(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    dept = await _make_department(db_session, "Phase10 空部门")

    result = await get_department_with_members(db_session, dept.id, tenant_id=TENANT_ID)

    assert result.members == []


async def test_admin_reports_group_by_department_aggregates_correctly(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    tech = await _make_user(db_session, UserRole.employee, name="Phase10 Tech", department="Phase10 技术部")
    sales = await _make_user(db_session, UserRole.employee, name="Phase10 Sales", department="Phase10 销售部")
    today = date.today()
    await _make_daily_report(db_session, tech.id, None, today, ai_score=80.0, pass_check=True)
    await _make_daily_report(db_session, tech.id, None, today, ai_score=60.0, pass_check=False)
    await _make_daily_report(db_session, sales.id, None, today, ai_score=90.0, pass_check=True)

    result = await group_reports_by_department(
        db_session,
        today - timedelta(days=7),
        today,
        project_id=None,
        tenant_id=TENANT_ID,
    )
    by_key = {row.key: row for row in result.groups}

    assert by_key["Phase10 技术部"].report_count == 2
    assert by_key["Phase10 技术部"].pass_count == 1
    assert by_key["Phase10 技术部"].avg_score == 70.0
    assert by_key["Phase10 技术部"].pass_rate == 50.0
    assert by_key["Phase10 销售部"].report_count == 1
    assert by_key["Phase10 销售部"].avg_score == 90.0
    assert by_key["Phase10 销售部"].pass_rate == 100.0


async def test_admin_reports_group_by_project_inner_join_excludes_null_project(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    user = await _make_user(db_session, UserRole.employee, name="Phase10 Project Reporter")
    project = await _make_project(db_session)
    today = date.today()
    await _make_daily_report(db_session, user.id, None, today, ai_score=50.0, pass_check=False)
    await _make_daily_report(db_session, user.id, project.id, today, ai_score=90.0, pass_check=True)

    result = await group_reports_by_project(
        db_session,
        today - timedelta(days=7),
        today,
        project_id=project.id,
        tenant_id=TENANT_ID,
    )

    assert len(result.groups) == 1
    assert result.groups[0].key == str(project.id)
    assert result.groups[0].report_count == 1
    assert result.groups[0].pass_rate == 100.0


async def test_validate_date_range_raises_when_start_after_end(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    today = date.today()

    with pytest.raises(ValueError, match="date_range_invalid"):
        _validate_date_range(today, today - timedelta(days=1))


async def test_router_dept_list_admin_returns_200(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    admin = await _make_user(db_session, UserRole.admin, name="Phase10 Dept Admin")

    resp = await client.get("/api/v1/admin/departments/", headers=_headers(admin))

    assert resp.status_code == 200


async def test_router_dept_list_manager_returns_200(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    manager = await _make_user(db_session, UserRole.manager, name="Phase10 Dept Manager")

    resp = await client.get("/api/v1/admin/departments/", headers=_headers(manager))

    assert resp.status_code == 200


async def test_router_dept_list_employee_returns_403(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    employee = await _make_user(db_session, UserRole.employee, name="Phase10 Dept Employee")

    resp = await client.get("/api/v1/admin/departments/", headers=_headers(employee))

    assert resp.status_code == 403


async def test_router_dept_create_name_conflict_returns_409(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    admin = await _make_user(db_session, UserRole.admin, name="Phase10 Dept Create Admin")
    payload = {"name": "Phase10 冲突部门"}

    first = await client.post("/api/v1/admin/departments/", json=payload, headers=_headers(admin))
    second = await client.post("/api/v1/admin/departments/", json=payload, headers=_headers(admin))

    assert first.status_code == 201
    assert second.status_code == 409


async def test_router_dept_create_invalid_manager_id_returns_400(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    admin = await _make_user(db_session, UserRole.admin, name="Phase10 Dept Manager Admin")

    resp = await client.post(
        "/api/v1/admin/departments/",
        json={"name": "Phase10 无负责人部门", "manager_id": str(uuid.uuid4())},
        headers=_headers(admin),
    )

    assert resp.status_code == 400


async def test_router_admin_reports_admin_dept_returns_200(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    admin = await _make_user(db_session, UserRole.admin, name="Phase10 Reports Admin")

    resp = await client.get("/api/v1/admin/reports/?group_by=department", headers=_headers(admin))

    assert resp.status_code == 200
    assert resp.json()["group_by"] == "department"


async def test_router_admin_reports_manager_project_returns_200(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    manager = await _make_user(db_session, UserRole.manager, name="Phase10 Reports Manager")

    resp = await client.get("/api/v1/admin/reports/?group_by=project", headers=_headers(manager))

    assert resp.status_code == 200
    assert resp.json()["group_by"] == "project"


async def test_router_admin_reports_employee_returns_403(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    employee = await _make_user(db_session, UserRole.employee, name="Phase10 Reports Employee")

    resp = await client.get("/api/v1/admin/reports/?group_by=department", headers=_headers(employee))

    assert resp.status_code == 403


async def test_router_admin_reports_invalid_group_by_returns_422(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    admin = await _make_user(db_session, UserRole.admin, name="Phase10 Reports Invalid Admin")

    resp = await client.get("/api/v1/admin/reports/?group_by=invalid", headers=_headers(admin))

    assert resp.status_code == 422


async def test_router_admin_reports_date_range_invalid_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase10_test_data(db_session)
    admin = await _make_user(db_session, UserRole.admin, name="Phase10 Reports Date Admin")
    today = date.today()

    resp = await client.get(
        f"/api/v1/admin/reports/?group_by=department&start_date={today.isoformat()}"
        f"&end_date={(today - timedelta(days=1)).isoformat()}",
        headers=_headers(admin),
    )

    assert resp.status_code == 400
    assert "start_date 不能晚于 end_date" in resp.json()["detail"]
