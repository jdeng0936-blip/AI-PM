from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.middleware.rbac import create_access_token
from app.models.daily_report import DailyReport
from app.models.project import Project, ProjectHealthStatus, ProjectStatus, ProjectTrack
from app.models.sprint import Sprint, SprintStatus
from app.models.user import User, UserRole
from tests._db_url import derive_test_database_url

TEST_DATABASE_URL = derive_test_database_url(settings.database_url)


@pytest_asyncio.fixture
async def client_and_db() -> AsyncGenerator[tuple[AsyncClient, AsyncSession], None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql("DROP MATERIALIZED VIEW IF EXISTS mv_weekly_dept_stats CASCADE")
        await conn.exec_driver_sql("DROP MATERIALIZED VIEW IF EXISTS mv_daily_user_stats CASCADE")

    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:

        async def _get_test_db():
            yield session

        app.dependency_overrides[get_db] = _get_test_db
        transport = ASGITransport(app=cast(Any, app))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, session
        app.dependency_overrides.clear()

    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP MATERIALIZED VIEW IF EXISTS mv_weekly_dept_stats CASCADE")
        await conn.exec_driver_sql("DROP MATERIALIZED VIEW IF EXISTS mv_daily_user_stats CASCADE")
    await engine.dispose()


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


async def _make_user(db: AsyncSession, role: UserRole, department: str, name: str) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"analytics_{uuid.uuid4().hex[:12]}",
        name=name,
        department=department,
        job_title="工程师",
        role=role,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_project(db: AsyncSession, owner: User) -> Project:
    project = Project(
        name="Phase 7 分析测试项目",
        code=f"AN-{uuid.uuid4().hex[:8].upper()}",
        track=ProjectTrack.software,
        status=ProjectStatus.active,
        health_score=82,
        health_status=ProjectHealthStatus.yellow,
        budget_total=Decimal("100000"),
        created_by=owner.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def _make_report(
    db: AsyncSession,
    user: User,
    report_date: date,
    score: int,
    pass_check: bool,
    project: Project | None = None,
    progress: int = 50,
) -> DailyReport:
    report = DailyReport(
        user_id=user.id,
        report_date=report_date,
        raw_input_text=f"{user.name} Phase 7 分析测试日报",
        parsed_content={"tasks": "趋势分析", "progress": progress},
        pass_check=pass_check,
        ai_score=score,
        project_id=project.id if project else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


async def _rebuild_analytics_views(db: AsyncSession) -> None:
    await db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_weekly_dept_stats CASCADE"))
    await db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_daily_user_stats CASCADE"))
    await db.execute(
        text(
            """
            CREATE MATERIALIZED VIEW mv_daily_user_stats AS
            SELECT
                dr.tenant_id,
                dr.user_id,
                u.name AS user_name,
                u.department,
                dr.report_date,
                COUNT(dr.id)::integer AS report_count,
                ROUND(AVG(dr.ai_score)::numeric, 2) AS avg_score,
                MAX(dr.ai_score) AS max_score,
                MIN(dr.ai_score) AS min_score,
                (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::integer AS pass_count,
                BOOL_OR(dr.pass_check IS TRUE) AS pass_check,
                TRUE AS submitted,
                MAX(dr.created_at) AS last_submitted_at,
                0::numeric AS submit_delay_minutes
            FROM daily_reports dr
            JOIN users u ON u.id = dr.user_id
            WHERE u.is_active = TRUE
              AND dr.deleted_at IS NULL
            GROUP BY dr.tenant_id, dr.user_id, u.name, u.department, dr.report_date
            WITH DATA
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE MATERIALIZED VIEW mv_weekly_dept_stats AS
            SELECT
                dr.tenant_id,
                u.department,
                DATE_TRUNC('week', dr.report_date::timestamp)::date AS week_start,
                COUNT(dr.id)::integer AS total_reports,
                COUNT(DISTINCT dr.user_id)::integer AS active_users,
                du.total_users,
                ROUND(AVG(dr.ai_score)::numeric, 2) AS avg_score,
                (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::integer AS pass_count,
                ROUND(
                    (
                        (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::numeric
                        / NULLIF(COUNT(dr.id), 0)
                        * 100
                    ),
                    2
                ) AS pass_rate,
                ROUND(
                    (
                        COUNT(DISTINCT dr.user_id)::numeric
                        / NULLIF(du.total_users, 0)
                        * 100
                    ),
                    2
                ) AS submitter_rate
            FROM daily_reports dr
            JOIN users u ON u.id = dr.user_id
            JOIN (
                SELECT tenant_id, department, COUNT(*)::integer AS total_users
                FROM users
                WHERE is_active = TRUE
                GROUP BY tenant_id, department
            ) du ON du.tenant_id = dr.tenant_id AND du.department = u.department
            WHERE u.is_active = TRUE
              AND dr.deleted_at IS NULL
            GROUP BY
                dr.tenant_id,
                u.department,
                DATE_TRUNC('week', dr.report_date::timestamp)::date,
                du.total_users
            WITH DATA
            """
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_user_trend_reads_materialized_view_and_enforces_employee_scope(client_and_db):
    client, db = client_and_db
    department = f"分析部-{uuid.uuid4().hex[:6]}"
    employee = await _make_user(db, UserRole.employee, department, "趋势员工A")
    other = await _make_user(db, UserRole.employee, department, "趋势员工B")

    today = date.today()
    await _make_report(db, employee, today - timedelta(days=1), 80, True)
    await _make_report(db, employee, today, 70, False)
    await _make_report(db, other, today, 95, True)
    await _rebuild_analytics_views(db)

    res = await client.get("/api/analytics/user-trend?days=30", headers=_headers(employee))
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == str(employee.id)
    assert body["summary"]["total_reports"] == 2
    assert body["summary"]["avg_score"] == 75.0
    assert body["summary"]["pass_rate"] == 50.0
    assert [point["avg_score"] for point in body["daily"]] == [80.0, 70.0]

    forbidden = await client.get(f"/api/analytics/user-trend?user_id={other.id}", headers=_headers(employee))
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_manager_analytics_endpoints(client_and_db):
    client, db = client_and_db
    department = f"研发分析部-{uuid.uuid4().hex[:6]}"
    manager = await _make_user(db, UserRole.manager, department, "分析经理")
    employee = await _make_user(db, UserRole.employee, department, "分析员工")
    project = await _make_project(db, manager)

    today = date.today()
    await _make_report(db, employee, today - timedelta(days=2), 88, True, project, progress=60)
    await _make_report(db, employee, today - timedelta(days=1), 92, True, project, progress=80)

    sprint = Sprint(
        project_id=project.id,
        sprint_number=3,
        goal="完成分析接口",
        start_date=today - timedelta(days=14),
        end_date=today - timedelta(days=1),
        planned_story_points=20,
        completed_story_points=16,
        health_score=84,
        status=SprintStatus.completed,
        created_by=manager.id,
    )
    db.add(sprint)
    await db.commit()
    await _rebuild_analytics_views(db)

    headers = _headers(manager)

    trend_res = await client.get(f"/api/analytics/user-trend?user_id={employee.id}&days=30", headers=headers)
    assert trend_res.status_code == 200
    assert trend_res.json()["summary"]["avg_score"] == 90.0

    dept_res = await client.get("/api/analytics/department-compare?period=week&weeks=4", headers=headers)
    assert dept_res.status_code == 200
    department_rows = [row for row in dept_res.json()["departments"] if row["department"] == department]
    assert department_rows
    assert department_rows[0]["latest_avg_score"] == 90.0
    assert department_rows[0]["latest_submitter_rate"] == 50.0

    project_res = await client.get(f"/api/analytics/project-health?project_id={project.id}&days=30", headers=headers)
    assert project_res.status_code == 200
    project_body = project_res.json()
    assert project_body["project_id"] == str(project.id)
    assert project_body["current_health_status"] == "yellow"
    assert [point["avg_progress"] for point in project_body["daily"]] == [60.0, 80.0]

    sprint_res = await client.get(
        f"/api/analytics/sprint-efficiency?project_id={project.id}&last_n=5",
        headers=headers,
    )
    assert sprint_res.status_code == 200
    sprint_body = sprint_res.json()
    assert sprint_body["count"] == 1
    assert sprint_body["summary"]["avg_velocity"] == 16.0
    assert sprint_body["sprints"][0]["completion_rate"] == 80.0
