from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.daily_report import DailyReport
from app.models.deletion_history import DeletionHistory
from app.models.knowledge import KnowledgeItem
from app.models.project import Project, ProjectTrack
from app.models.project_member import MemberTrack, ProjectMember
from app.models.risk_alert import RiskAlert
from app.models.sprint import Sprint
from app.models.sprint_task import SprintTask
from app.models.user import User, UserRole
from app.services.deletion_cleanup import build_deletion_cleanup_dry_run, render_deletion_cleanup_dry_run_markdown
from tests.conftest import TEST_DATABASE_URL


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """本地 fixture:engine 在 test 自己的 event loop 内构造,
    规避 conftest 全局 db_session 因 pytest-asyncio 1.x loop_scope
    不对齐导致的 'Future attached to a different loop' 问题。
    autouse 的 setup_test_db 已建表,这里只做 session 隔离 + 结束回滚。
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


def test_render_deletion_cleanup_dry_run_markdown_contains_tables_and_impacts():
    markdown = render_deletion_cleanup_dry_run_markdown(
        {
            "mode": "dry_run",
            "retention_days": 30,
            "generated_at": "2026-05-26T13:30:00+00:00",
            "cutoff": "2026-04-26T13:30:00+00:00",
            "tables": {
                "daily_reports": 2,
                "projects": 1,
                "sprint_tasks": 3,
                "risk_alerts": 4,
                "knowledge_items": 5,
            },
            "impacts": {
                "risk_alerts_cascade_from_daily_reports": 6,
                "daily_reports_detach_from_projects": 7,
                "knowledge_items_detach_from_projects": 8,
                "project_members_cascade_from_projects": 9,
                "daily_reports_detach_from_sprint_tasks": 10,
            },
            "open_history_batches": 11,
            "total_candidates": 15,
        }
    )

    assert "dry-run,不会硬删数据" in markdown
    assert "日报: 2 条" in markdown
    assert "临时项目: 1 个" in markdown
    assert "未恢复 deletion_history 批次: 11 批" in markdown
    assert "日报硬删将级联 RiskAlert: 6 条" in markdown
    assert "任务硬删将解绑日报任务关联: 10 条" in markdown


@pytest.mark.asyncio
async def test_build_deletion_cleanup_dry_run_integration(db_session: AsyncSession):
    """V2.6 软删过期清理 dry-run 集成测试。

    复用 conftest 的 db_session fixture(autouse 已建表 + 函数级回滚),
    通过 db_session.flush() 让 INSERT 立即对当前事务内的 SELECT 可见,
    测试结束时 fixture 自动 rollback,不污染测试库。

    覆盖三种 deleted_at 边界:None(活跃) / cutoff 前(过期) / cutoff 后(保留),
    并验证 cascade/detach 五项级联计数全部精确。
    """
    now_dt = datetime(2026, 5, 27, 8, 0, 0, tzinfo=timezone.utc)
    cutoff = now_dt - timedelta(days=30)
    expired_at = cutoff - timedelta(days=5)
    recent_at = cutoff + timedelta(days=5)

    # 1. user — 所有 created_by/user_id 都指向这个测试用户
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"test_cleanup_user_{uuid.uuid4().hex[:8]}",
        name="清理测试员",
        department="测试部",
        job_title="工程师",
        role=UserRole.admin,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    # 2. projects — 4 种状态,只有「过期临时」才进 tables.projects
    code_salt = uuid.uuid4().hex[:6]  # projects.code 是 VARCHAR(16),整体凑短
    p_active = Project(
        id=uuid.uuid4(),
        name="活跃普通项目",
        code=f"AC_{code_salt}",
        is_temporary=False,
        track=ProjectTrack.dual,
        created_by=user.id,
    )
    p_expired_temp = Project(
        id=uuid.uuid4(),
        name="已过期临时项目",
        code=f"ET_{code_salt}",
        is_temporary=True,
        track=ProjectTrack.other,
        deleted_at=expired_at,
        created_by=user.id,
    )
    p_recent_temp = Project(
        id=uuid.uuid4(),
        name="未过期临时项目",
        code=f"RT_{code_salt}",
        is_temporary=True,
        track=ProjectTrack.other,
        deleted_at=recent_at,
        created_by=user.id,
    )
    # 主干项目即使过期软删也不算 projects 候选(必须 is_temporary=True 才计)
    p_expired_master = Project(
        id=uuid.uuid4(),
        name="已过期主干项目",
        code=f"EM_{code_salt}",
        is_temporary=False,
        track=ProjectTrack.software,
        deleted_at=expired_at,
        created_by=user.id,
    )
    db_session.add_all([p_active, p_expired_temp, p_recent_temp, p_expired_master])
    await db_session.flush()

    # 3. sprint + sprint tasks(一过期一活跃)
    sprint = Sprint(
        id=uuid.uuid4(),
        project_id=p_active.id,
        sprint_number=1,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 14),
        created_by=user.id,
    )
    db_session.add(sprint)
    await db_session.flush()

    task_expired = SprintTask(
        id=uuid.uuid4(),
        sprint_id=sprint.id,
        title="已过期软删任务",
        deleted_at=expired_at,
        created_by=user.id,
    )
    task_active = SprintTask(
        id=uuid.uuid4(),
        sprint_id=sprint.id,
        title="活跃任务",
        created_by=user.id,
    )
    db_session.add_all([task_expired, task_active])
    await db_session.flush()

    # 4. daily reports — r_expired 同时挂在 p_expired_temp 和 task_expired 上,
    #    用于触发 detach_from_projects / detach_from_sprint_tasks 两条 impact
    r_expired = DailyReport(
        id=uuid.uuid4(),
        user_id=user.id,
        report_date=date(2026, 5, 1),
        raw_input_text="已过期日报",
        deleted_at=expired_at,
        project_id=p_expired_temp.id,
        sprint_task_id=task_expired.id,
        created_by=user.id,
    )
    r_active = DailyReport(
        id=uuid.uuid4(),
        user_id=user.id,
        report_date=date(2026, 5, 20),
        raw_input_text="活跃日报",
        created_by=user.id,
    )
    db_session.add_all([r_expired, r_active])
    await db_session.flush()

    # 5. risk alerts — 两条都指向 r_expired,触发 cascade_from_daily_reports=2
    alert_expired = RiskAlert(
        id=uuid.uuid4(),
        report_id=r_expired.id,
        user_id=user.id,
        description="已过期预警",
        deleted_at=expired_at,
        created_by=user.id,
    )
    alert_cascade = RiskAlert(
        id=uuid.uuid4(),
        report_id=r_expired.id,
        user_id=user.id,
        description="级联影响预警",
        created_by=user.id,
    )
    db_session.add_all([alert_expired, alert_cascade])
    await db_session.flush()

    # 6. knowledge items — 一过期一挂在过期项目下
    k_expired = KnowledgeItem(
        id=uuid.uuid4(),
        title="已过期知识点",
        category="faq",
        content="已过期知识点内容",
        deleted_at=expired_at,
        created_by=user.id,
    )
    k_detached = KnowledgeItem(
        id=uuid.uuid4(),
        title="解绑项目知识点",
        category="wiki",
        content="解绑内容",
        project_id=p_expired_temp.id,
        created_by=user.id,
    )
    db_session.add_all([k_expired, k_detached])
    await db_session.flush()

    # 7. project member(挂在过期临时项目上,触发 project_members_cascade)
    member = ProjectMember(
        id=uuid.uuid4(),
        project_id=p_expired_temp.id,
        user_id=user.id,
        track=MemberTrack.software,
        created_by=user.id,
    )
    db_session.add(member)
    await db_session.flush()

    # 8. deletion_history — expires_at < now 且未恢复未硬删,算 open_history_batches=1
    history = DeletionHistory(
        id=uuid.uuid4(),
        actor_id=user.id,
        table_name="daily_reports",
        record_ids=[str(r_expired.id)],
        deleted_at=expired_at,
        expires_at=expired_at + timedelta(days=30),
        created_by=user.id,
    )
    db_session.add(history)
    await db_session.flush()

    # 9. 执行 dry-run
    stats = await build_deletion_cleanup_dry_run(db_session, now=now_dt)

    # 10. 校验顶层字段
    assert stats["mode"] == "dry_run"
    assert stats["retention_days"] == 30
    assert stats["cutoff"] == cutoff.isoformat()
    assert stats["generated_at"] == now_dt.isoformat()

    # tables: 每张表只数一条过期对象
    assert stats["tables"]["daily_reports"] == 1
    assert stats["tables"]["projects"] == 1  # 仅 p_expired_temp;p_expired_master 因 is_temporary=False 被排除
    assert stats["tables"]["sprint_tasks"] == 1
    assert stats["tables"]["risk_alerts"] == 1
    assert stats["tables"]["knowledge_items"] == 1
    assert stats["total_candidates"] == 5

    # impacts: 五项级联/解绑精确计数
    assert (
        stats["impacts"]["risk_alerts_cascade_from_daily_reports"] == 2
    )  # alert_expired + alert_cascade 均挂 r_expired
    assert stats["impacts"]["daily_reports_detach_from_projects"] == 1  # r_expired 挂 p_expired_temp
    assert stats["impacts"]["knowledge_items_detach_from_projects"] == 1  # k_detached 挂 p_expired_temp
    assert stats["impacts"]["project_members_cascade_from_projects"] == 1  # member 挂 p_expired_temp
    assert stats["impacts"]["daily_reports_detach_from_sprint_tasks"] == 1  # r_expired 挂 task_expired

    # open history batches
    assert stats["open_history_batches"] == 1
