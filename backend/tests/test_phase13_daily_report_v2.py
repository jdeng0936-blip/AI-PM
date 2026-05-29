"""T-1301 tests: daily report morning-evening loop and supervised tracking."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
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
from app.models.daily_report import DailyReport, PlannedStatus, ReportType
from app.models.daily_supervised_task import DailySupervisedTask, SupervisedStatus
from app.models.project import Project, ProjectHealthStatus, ProjectStatus, ProjectTrack
from app.models.project_followup import ProjectFollowUp
from app.models.project_member import MemberTrack, ProjectMember
from app.models.sprint import Sprint as SprintModel
from app.models.sprint import SprintStatus
from app.models.sprint_task import SprintTask, TaskPriority, TaskStatus
from app.models.user import User, UserRole
from tests._db_url import derive_test_database_url

pytestmark = pytest.mark.asyncio

TENANT_ID = "default"
OTHER_TENANT_ID = "phase13_other"
PHASE13_PREFIX = "phase13"
TEST_DATABASE_URL = derive_test_database_url(settings.database_url)


async def _phase13_prepare_schema(conn: Any) -> None:
    await conn.execute(
        text(
            """
            DO $$ BEGIN
                CREATE TYPE daily_report_type AS ENUM ('morning_plan', 'evening_review', 'ad_hoc');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    await conn.execute(
        text(
            """
            DO $$ BEGIN
                CREATE TYPE daily_report_planned_status AS ENUM ('done', 'partial', 'delayed', 'cancelled');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    await conn.execute(
        text(
            """
            DO $$ BEGIN
                CREATE TYPE supervised_status AS ENUM ('open', 'closed');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE IF EXISTS daily_reports ADD COLUMN IF NOT EXISTS report_type daily_report_type NOT NULL DEFAULT 'ad_hoc'"
        )
    )
    await conn.execute(text("ALTER TABLE IF EXISTS daily_reports ADD COLUMN IF NOT EXISTS parent_plan_id UUID NULL"))
    await conn.execute(
        text(
            "ALTER TABLE IF EXISTS daily_reports ADD COLUMN IF NOT EXISTS planned_status daily_report_planned_status NULL"
        )
    )
    await conn.execute(
        text("ALTER TABLE IF EXISTS daily_reports ADD COLUMN IF NOT EXISTS work_tags VARCHAR[] NULL DEFAULT '{}'")
    )
    await conn.execute(
        text(
            """
            DO $$ BEGIN
                IF to_regclass('daily_reports') IS NOT NULL THEN
                    ALTER TABLE daily_reports
                    ADD CONSTRAINT fk_daily_reports_parent_plan_id
                    FOREIGN KEY (parent_plan_id) REFERENCES daily_reports(id) ON DELETE SET NULL;
                END IF;
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )


async def _cleanup_phase13_test_data(db_session: AsyncSession) -> None:
    phase13_user_ids = select(User.id).where(User.wechat_userid.like(f"{PHASE13_PREFIX}_%"))
    phase13_project_ids = select(Project.id).where(Project.code.like(f"{PHASE13_PREFIX}_%"))
    phase13_report_ids = select(DailyReport.id).where(
        or_(
            DailyReport.user_id.in_(phase13_user_ids),
            DailyReport.raw_input_text.like(f"%{PHASE13_PREFIX}%"),
            DailyReport.project_id.in_(phase13_project_ids),
        )
    )
    phase13_sprint_ids = select(SprintModel.id).where(SprintModel.project_id.in_(phase13_project_ids))

    await db_session.execute(
        delete(DailySupervisedTask).where(
            or_(
                DailySupervisedTask.user_id.in_(phase13_user_ids),
                DailySupervisedTask.source_report_id.in_(phase13_report_ids),
            )
        )
    )
    await db_session.execute(
        delete(ProjectFollowUp).where(
            or_(
                ProjectFollowUp.created_by.in_(phase13_user_ids),
                ProjectFollowUp.project_id.in_(phase13_project_ids),
                ProjectFollowUp.content.like("[督导] phase13%"),
            )
        )
    )
    await db_session.execute(delete(DailyReport).where(DailyReport.id.in_(phase13_report_ids)))
    await db_session.execute(
        delete(ProjectMember).where(
            or_(
                ProjectMember.user_id.in_(phase13_user_ids),
                ProjectMember.project_id.in_(phase13_project_ids),
            )
        )
    )
    await db_session.execute(delete(SprintTask).where(SprintTask.sprint_id.in_(phase13_sprint_ids)))
    await db_session.execute(delete(SprintModel).where(SprintModel.id.in_(phase13_sprint_ids)))
    await db_session.execute(delete(Project).where(Project.id.in_(phase13_project_ids)))
    await db_session.execute(delete(User).where(User.id.in_(phase13_user_ids)))
    await db_session.flush()


def _phase13_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


async def _phase13_make_user(
    db_session: AsyncSession,
    *,
    wechat_userid: str,
    role: UserRole = UserRole.employee,
    tenant_id: str = TENANT_ID,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=wechat_userid,
        name=wechat_userid,
        department="phase13_dept",
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


async def _phase13_make_project(
    db_session: AsyncSession,
    *,
    creator: User,
    code: str,
    status: ProjectStatus = ProjectStatus.active,
    tenant_id: str = TENANT_ID,
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=f"{code}_project",
        code=code,
        description="phase13 project",
        track=ProjectTrack.dual,
        status=status,
        health_status=ProjectHealthStatus.green,
        health_score=100,
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.refresh(project)
    return project


async def _phase13_make_member(
    db_session: AsyncSession,
    *,
    project: Project,
    user: User,
    creator: User,
    tenant_id: str = TENANT_ID,
) -> ProjectMember:
    member = ProjectMember(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=user.id,
        track=MemberTrack.both,
        role_in_project="phase13_member",
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    db_session.add(member)
    await db_session.flush()
    await db_session.refresh(member)
    return member


async def _phase13_make_iteration(
    db_session: AsyncSession,
    *,
    project: Project,
    creator: User,
    tenant_id: str = TENANT_ID,
) -> SprintModel:
    sprint = SprintModel(
        id=uuid.uuid4(),
        project_id=project.id,
        sprint_number=1,
        goal="phase13 sprint",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=14),
        status=SprintStatus.active,
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    db_session.add(sprint)
    await db_session.flush()
    await db_session.refresh(sprint)
    return sprint


async def _phase13_make_task(
    db_session: AsyncSession,
    *,
    sprint: SprintModel,
    assignee: User,
    title: str = "phase13 task",
    status: TaskStatus = TaskStatus.todo,
    tenant_id: str = TENANT_ID,
) -> SprintTask:
    task = SprintTask(
        id=uuid.uuid4(),
        sprint_id=sprint.id,
        assignee_id=assignee.id,
        title=title,
        story_points=3,
        status=status,
        priority=TaskPriority.p1,
        is_on_critical_path=False,
        planned_end=date.today() + timedelta(days=3),
        tenant_id=tenant_id,
        created_by=assignee.id,
    )
    db_session.add(task)
    await db_session.flush()
    await db_session.refresh(task)
    return task


async def _phase13_make_report(
    db_session: AsyncSession,
    *,
    user: User,
    report_type: ReportType = ReportType.morning_plan,
    planned_status: PlannedStatus | None = None,
    parent_plan_id: uuid.UUID | None = None,
    project: Project | None = None,
    task: SprintTask | None = None,
    raw_input_text: str = "phase13 report",
    tenant_id: str | None = None,
) -> DailyReport:
    report = DailyReport(
        id=uuid.uuid4(),
        user_id=user.id,
        report_date=date.today(),
        raw_input_text=raw_input_text,
        media_urls=[],
        parsed_content={"tasks": raw_input_text},
        pass_check=True,
        report_type=report_type,
        parent_plan_id=parent_plan_id,
        planned_status=planned_status,
        project_id=project.id if project else None,
        sprint_task_id=task.id if task else None,
        work_tags=["研发"],
        tenant_id=tenant_id or user.tenant_id,
        created_by=user.id,
    )
    db_session.add(report)
    await db_session.flush()
    await db_session.refresh(report)
    return report


async def _phase13_make_supervised(
    db_session: AsyncSession,
    *,
    user: User,
    source_report: DailyReport,
    project: Project | None = None,
    task: SprintTask | None = None,
    status: SupervisedStatus = SupervisedStatus.open,
    tenant_id: str | None = None,
) -> DailySupervisedTask:
    supervised = DailySupervisedTask(
        id=uuid.uuid4(),
        user_id=user.id,
        project_id=project.id if project else None,
        sprint_task_id=task.id if task else None,
        source_report_id=source_report.id,
        status=status,
        closed_at=datetime.now(timezone.utc) if status == SupervisedStatus.closed else None,
        tenant_id=tenant_id or user.tenant_id,
        created_by=user.id,
    )
    db_session.add(supervised)
    await db_session.flush()
    await db_session.refresh(supervised)
    return supervised


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await _phase13_prepare_schema(conn)
        await conn.run_sync(Base.metadata.create_all)
        await _phase13_prepare_schema(conn)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        await _cleanup_phase13_test_data(session)
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
            await _cleanup_phase13_test_data(session)
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


async def _phase13_project_with_task(
    db_session: AsyncSession,
    *,
    suffix: str,
    user: User,
    status: ProjectStatus = ProjectStatus.active,
    task_status: TaskStatus = TaskStatus.todo,
    tenant_id: str = TENANT_ID,
) -> tuple[Project, SprintModel, SprintTask]:
    project = await _phase13_make_project(
        db_session,
        creator=user,
        code=f"phase13_{suffix}",
        status=status,
        tenant_id=tenant_id,
    )
    await _phase13_make_member(db_session, project=project, user=user, creator=user, tenant_id=tenant_id)
    sprint = await _phase13_make_iteration(db_session, project=project, creator=user, tenant_id=tenant_id)
    task = await _phase13_make_task(
        db_session,
        sprint=sprint,
        assignee=user,
        title=f"phase13_task_{suffix}",
        status=task_status,
        tenant_id=tenant_id,
    )
    return project, sprint, task


async def test_daily_report_report_type_enum_persisted(db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_enum_user")

    morning = await _phase13_make_report(
        db_session, user=user, report_type=ReportType.morning_plan, raw_input_text="phase13_enum_morning"
    )
    evening = await _phase13_make_report(
        db_session,
        user=user,
        report_type=ReportType.evening_review,
        planned_status=PlannedStatus.done,
        raw_input_text="phase13_enum_evening",
    )
    default_report = DailyReport(
        id=uuid.uuid4(),
        user_id=user.id,
        report_date=date.today(),
        raw_input_text="phase13_enum_default",
        media_urls=[],
        parsed_content={},
        pass_check=True,
        tenant_id=user.tenant_id,
        created_by=user.id,
    )
    db_session.add(default_report)
    await db_session.commit()

    assert morning.report_type == ReportType.morning_plan
    assert evening.report_type == ReportType.evening_review
    saved_default = await db_session.scalar(select(DailyReport).where(DailyReport.id == default_report.id))
    assert saved_default is not None
    assert saved_default.report_type == ReportType.ad_hoc


async def test_daily_report_parent_plan_id_self_fk_set_null_on_delete(db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_self_fk_user")
    parent = await _phase13_make_report(db_session, user=user, raw_input_text="phase13_parent")
    evening = await _phase13_make_report(
        db_session,
        user=user,
        report_type=ReportType.evening_review,
        parent_plan_id=parent.id,
        planned_status=PlannedStatus.done,
        raw_input_text="phase13_child",
    )
    parent.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    after_soft = await db_session.scalar(select(DailyReport).where(DailyReport.id == evening.id))
    assert after_soft is not None
    assert after_soft.parent_plan_id == parent.id

    evening_id = evening.id
    await db_session.execute(delete(DailyReport).where(DailyReport.id == parent.id))
    await db_session.commit()
    db_session.expire(evening)
    after_hard = await db_session.scalar(select(DailyReport).where(DailyReport.id == evening_id))
    assert after_hard is not None
    assert after_hard.parent_plan_id is None


async def test_daily_supervised_task_cascade_on_source_report_delete(db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_cascade_user")
    source = await _phase13_make_report(
        db_session,
        user=user,
        report_type=ReportType.evening_review,
        planned_status=PlannedStatus.partial,
        raw_input_text="phase13_cascade_source",
    )
    await _phase13_make_supervised(db_session, user=user, source_report=source)
    await db_session.commit()

    await db_session.execute(delete(DailyReport).where(DailyReport.id == source.id))
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(DailySupervisedTask))
    assert int(count or 0) == 0


async def test_my_active_returns_active_projects_with_open_tasks(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_active_user")
    project, _, task = await _phase13_project_with_task(db_session, suffix="act1", user=user)
    await db_session.commit()

    res = await client.get("/api/v1/reports/projects/my-active", headers=_phase13_headers(user))

    assert res.status_code == 200
    data = res.json()
    assert data["total_projects"] == 1
    assert data["projects"][0]["id"] == str(project.id)
    assert data["projects"][0]["tasks"][0]["id"] == str(task.id)


async def test_my_active_excludes_completed_projects(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_completed_user")
    await _phase13_project_with_task(db_session, suffix="donep", user=user, status=ProjectStatus.completed)
    await db_session.commit()

    res = await client.get("/api/v1/reports/projects/my-active", headers=_phase13_headers(user))

    assert res.status_code == 200
    assert res.json()["total_projects"] == 0


async def test_my_active_excludes_done_tasks(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_done_task_user")
    await _phase13_project_with_task(db_session, suffix="donet", user=user, task_status=TaskStatus.done)
    await db_session.commit()

    res = await client.get("/api/v1/reports/projects/my-active", headers=_phase13_headers(user))

    assert res.status_code == 200
    project = res.json()["projects"][0]
    assert project["tasks"] == []


async def test_my_active_tenant_isolation(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    owner = await _phase13_make_user(db_session, wechat_userid="phase13_tenant_owner")
    other = await _phase13_make_user(
        db_session,
        wechat_userid="phase13_tenant_other",
        tenant_id=OTHER_TENANT_ID,
    )
    await _phase13_project_with_task(db_session, suffix="tenant", user=owner)
    await db_session.commit()

    res = await client.get("/api/v1/reports/projects/my-active", headers=_phase13_headers(other))

    assert res.status_code == 200
    assert res.json()["total_projects"] == 0


async def test_morning_batch_inserts_morning_plan_rows(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_morning_user")
    project, _, task = await _phase13_project_with_task(db_session, suffix="mbatch", user=user)
    await db_session.commit()

    res = await client.post(
        "/api/v1/reports/morning-batch",
        headers=_phase13_headers(user),
        json={
            "items": [
                {
                    "project_id": str(project.id),
                    "sprint_task_id": str(task.id),
                    "work_tags": ["研发"],
                    "note": "phase13_task_note",
                },
                {"project_id": str(project.id), "work_tags": ["沟通"], "note": "phase13_project_note"},
                {"work_tags": ["文档"], "note": "phase13_ad_hoc_note"},
            ]
        },
    )

    assert res.status_code == 200
    assert res.json()["inserted"] == 3
    reports = (
        (
            await db_session.execute(
                select(DailyReport).where(
                    DailyReport.user_id == user.id,
                    DailyReport.report_type == ReportType.morning_plan,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(reports) == 3
    assert any(report.work_tags == ["研发"] for report in reports)


async def test_morning_batch_ad_hoc_card_requires_note(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_empty_card_user")
    await db_session.commit()

    res = await client.post(
        "/api/v1/reports/morning-batch",
        headers=_phase13_headers(user),
        json={"items": [{"work_tags": ["研发"]}]},
    )

    assert res.status_code == 422


async def test_morning_batch_rejects_unauthorized_project(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    owner = await _phase13_make_user(db_session, wechat_userid="phase13_project_owner")
    user = await _phase13_make_user(db_session, wechat_userid="phase13_project_outsider")
    project = await _phase13_make_project(db_session, creator=owner, code="phase13_unauth")
    await db_session.commit()

    res = await client.post(
        "/api/v1/reports/morning-batch",
        headers=_phase13_headers(user),
        json={"items": [{"project_id": str(project.id), "note": "phase13_no_access"}]},
    )

    assert res.status_code in {403, 404}


async def test_evening_batch_done_does_not_create_supervised(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_done_user")
    project, _, task = await _phase13_project_with_task(db_session, suffix="edone", user=user)
    parent = await _phase13_make_report(
        db_session, user=user, project=project, task=task, raw_input_text="phase13_done_parent"
    )
    await db_session.commit()

    res = await client.post(
        "/api/v1/reports/evening-batch",
        headers=_phase13_headers(user),
        json={
            "reviews": [{"parent_report_id": str(parent.id), "planned_status": "done", "actual_note": "phase13_done"}]
        },
    )

    assert res.status_code == 200
    assert res.json()["supervised_created"] == 0
    count = await db_session.scalar(select(func.count()).select_from(DailySupervisedTask))
    assert int(count or 0) == 0


async def test_evening_batch_partial_creates_supervised_and_followup(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_partial_user")
    project, _, task = await _phase13_project_with_task(db_session, suffix="epart", user=user)
    parent = await _phase13_make_report(
        db_session, user=user, project=project, task=task, raw_input_text="phase13_partial_parent"
    )
    await db_session.commit()

    res = await client.post(
        "/api/v1/reports/evening-batch",
        headers=_phase13_headers(user),
        json={
            "reviews": [
                {"parent_report_id": str(parent.id), "planned_status": "partial", "actual_note": "phase13_blocked"}
            ]
        },
    )

    assert res.status_code == 200
    assert res.json()["supervised_created"] == 1
    supervised_count = await db_session.scalar(select(func.count()).select_from(DailySupervisedTask))
    followup = await db_session.scalar(select(ProjectFollowUp).where(ProjectFollowUp.project_id == project.id))
    assert int(supervised_count or 0) == 1
    assert followup is not None
    assert "[督导]" in followup.content


async def test_evening_batch_done_auto_closes_existing_supervised(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_close_user")
    project, _, task = await _phase13_project_with_task(db_session, suffix="eclose", user=user)
    old_source = await _phase13_make_report(
        db_session,
        user=user,
        report_type=ReportType.evening_review,
        planned_status=PlannedStatus.partial,
        project=project,
        task=task,
        raw_input_text="phase13_old_source",
    )
    supervised = await _phase13_make_supervised(
        db_session,
        user=user,
        source_report=old_source,
        project=project,
        task=task,
    )
    parent = await _phase13_make_report(
        db_session, user=user, project=project, task=task, raw_input_text="phase13_new_parent"
    )
    await db_session.commit()

    res = await client.post(
        "/api/v1/reports/evening-batch",
        headers=_phase13_headers(user),
        json={
            "reviews": [
                {"parent_report_id": str(parent.id), "planned_status": "done", "actual_note": "phase13_done_now"}
            ]
        },
    )

    assert res.status_code == 200
    assert res.json()["supervised_closed"] == 1
    saved = await db_session.scalar(select(DailySupervisedTask).where(DailySupervisedTask.id == supervised.id))
    assert saved is not None
    assert saved.status == SupervisedStatus.closed
    assert saved.closed_by_report_id is not None


async def test_evening_batch_extras_create_ad_hoc_rows(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_extras_user")
    await db_session.commit()

    res = await client.post(
        "/api/v1/reports/evening-batch",
        headers=_phase13_headers(user),
        json={"extras": [{"note": "phase13_extra_a"}, {"note": "phase13_extra_b", "work_tags": ["学习"]}]},
    )

    assert res.status_code == 200
    assert res.json()["extra_count"] == 2
    reports = (
        (
            await db_session.execute(
                select(DailyReport).where(
                    DailyReport.user_id == user.id,
                    DailyReport.report_type == ReportType.ad_hoc,
                    DailyReport.raw_input_text.like("[晚复盘/自主新增]%"),
                )
            )
        )
        .scalars()
        .all()
    )
    supervised_count = await db_session.scalar(select(func.count()).select_from(DailySupervisedTask))
    assert len(reports) == 2
    assert all(report.parent_plan_id is None for report in reports)
    assert int(supervised_count or 0) == 0


async def test_pending_follow_ups_returns_open_only(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    user = await _phase13_make_user(db_session, wechat_userid="phase13_pending_user")
    project, _, task = await _phase13_project_with_task(db_session, suffix="pend", user=user)
    source = await _phase13_make_report(
        db_session,
        user=user,
        report_type=ReportType.evening_review,
        planned_status=PlannedStatus.partial,
        project=project,
        task=task,
        raw_input_text="phase13_pending_source",
    )
    await _phase13_make_supervised(db_session, user=user, source_report=source, project=project, task=task)
    await _phase13_make_supervised(db_session, user=user, source_report=source, project=project, task=task)
    await _phase13_make_supervised(
        db_session,
        user=user,
        source_report=source,
        project=project,
        task=task,
        status=SupervisedStatus.closed,
    )
    await db_session.commit()

    res = await client.get("/api/v1/reports/pending-follow-ups", headers=_phase13_headers(user))

    assert res.status_code == 200
    assert res.json()["total"] == 2


async def test_pending_follow_ups_tenant_isolation(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase13_test_data(db_session)
    owner = await _phase13_make_user(db_session, wechat_userid="phase13_pending_owner")
    other = await _phase13_make_user(
        db_session,
        wechat_userid="phase13_pending_other",
        tenant_id=OTHER_TENANT_ID,
    )
    source = await _phase13_make_report(
        db_session,
        user=owner,
        report_type=ReportType.evening_review,
        planned_status=PlannedStatus.partial,
        raw_input_text="phase13_pending_tenant_source",
    )
    await _phase13_make_supervised(db_session, user=owner, source_report=source)
    await db_session.commit()

    res = await client.get("/api/v1/reports/pending-follow-ups", headers=_phase13_headers(other))

    assert res.status_code == 200
    assert res.json()["total"] == 0
