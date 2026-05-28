"""tests/test_daily_report_relations.py — V2.2 daily_reports 项目/任务 FK 关联

测试目标:
  1. _validate_project_task_consistency 5 个分支全覆盖
  2. DailyReport 可以正确存储 + 查询 project_id + sprint_task_id
  3. project_id / sprint_task_id 均可 NULL(向后兼容)

只测核心校验逻辑,不涉及 AI 调用。
fixture 模式参考 tests/test_capacity.py(独立 engine + Session,避免 conftest 的
nested begin 与 asyncpg 冲突)。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.daily_report import DailyReport
from app.models.project import Project, ProjectTrack
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import SprintTask, TaskPriority, TaskStatus
from app.models.user import User, UserRole
from app.routers.simulate import _validate_project_task_consistency
from tests._db_url import derive_test_database_url

TEST_DATABASE_URL = derive_test_database_url(settings.database_url)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════
# Helpers — 建测试对象
# ═══════════════════════════════════════════════════════════════════


async def _make_user(db: AsyncSession) -> User:
    user = User(
        wechat_userid=f"ut_dr_{uuid.uuid4().hex[:8]}",
        name="测试员",
        department="测试部",
        job_title="工程师",
        role=UserRole.employee,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_project(db: AsyncSession, code: str = None) -> Project:
    proj = Project(
        name="V2.2 测试项目",
        code=code or f"UT-{uuid.uuid4().hex[:6].upper()}",
        track=ProjectTrack.software,
        current_stage=3,
        budget_total=Decimal("100000"),
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return proj


async def _make_sprint(db: AsyncSession, project_id: uuid.UUID) -> Sprint:
    sp = Sprint(
        project_id=project_id,
        sprint_number=1,
        goal="UT sprint",
        start_date=date.today() - timedelta(days=7),
        end_date=date.today() + timedelta(days=7),
        status=SprintStatus.active,
    )
    db.add(sp)
    await db.commit()
    await db.refresh(sp)
    return sp


async def _make_task(db: AsyncSession, sprint_id: uuid.UUID, title: str = "UT task") -> SprintTask:
    t = SprintTask(
        sprint_id=sprint_id,
        title=title,
        story_points=3,
        status=TaskStatus.todo,
        priority=TaskPriority.p2,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


# ═══════════════════════════════════════════════════════════════════
# _validate_project_task_consistency 的 5 个分支
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_validate_both_none_is_ok(db):
    """case 1: 两个都不传 → OK(员工写"不挂钩"的日报)"""
    await _validate_project_task_consistency(db, None, None)  # 不抛即通过


@pytest.mark.asyncio
async def test_validate_only_project_is_ok(db):
    """case 2: 只传 project_id → OK(只挂项目不挂具体任务)"""
    proj = await _make_project(db)
    await _validate_project_task_consistency(db, proj.id, None)


@pytest.mark.asyncio
async def test_validate_task_belongs_to_project_is_ok(db):
    """case 3: 同时传 + 一致 → OK"""
    proj = await _make_project(db)
    sp = await _make_sprint(db, proj.id)
    task = await _make_task(db, sp.id)
    await _validate_project_task_consistency(db, proj.id, task.id)


@pytest.mark.asyncio
async def test_validate_task_in_different_project_raises_400(db):
    """case 4: 同时传,但 task 属于另一个项目 → 400"""
    proj_a = await _make_project(db, code=f"UT-A-{uuid.uuid4().hex[:4]}")
    proj_b = await _make_project(db, code=f"UT-B-{uuid.uuid4().hex[:4]}")
    sp_a = await _make_sprint(db, proj_a.id)
    task_a = await _make_task(db, sp_a.id)

    with pytest.raises(HTTPException) as exc:
        await _validate_project_task_consistency(db, proj_b.id, task_a.id)
    assert exc.value.status_code == 400
    assert "不属于" in exc.value.detail


@pytest.mark.asyncio
async def test_validate_nonexistent_task_raises_404(db):
    """case 5: sprint_task_id 不存在 → 404"""
    fake_task_id = uuid.uuid4()
    with pytest.raises(HTTPException) as exc:
        await _validate_project_task_consistency(db, None, fake_task_id)
    assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# DailyReport 模型层
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_daily_report_persists_project_and_task_fk(db):
    """直接 ORM 落 daily_report,project_id + sprint_task_id 能被读回。"""
    user = await _make_user(db)
    proj = await _make_project(db)
    sp = await _make_sprint(db, proj.id)
    task = await _make_task(db, sp.id, title="联调 MQTT 接入")

    report = DailyReport(
        user_id=user.id,
        report_date=date.today(),
        raw_input_text="今天联调了 MQTT 接入。",
        parsed_content={"tasks": "MQTT 联调", "progress": 80},
        pass_check=True,
        ai_score=85,
        project_id=proj.id,
        sprint_task_id=task.id,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    fetched = (await db.execute(select(DailyReport).where(DailyReport.id == report.id))).scalar_one()
    assert fetched.project_id == proj.id
    assert fetched.sprint_task_id == task.id


@pytest.mark.asyncio
async def test_daily_report_allows_null_fk(db):
    """两个 FK 都 nullable,不挂钩也能落库(老数据兼容)。"""
    user = await _make_user(db)
    report = DailyReport(
        user_id=user.id,
        report_date=date.today(),
        raw_input_text="今天什么都没挂。",
        parsed_content={},
        pass_check=True,
        ai_score=70,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    assert report.project_id is None
    assert report.sprint_task_id is None
