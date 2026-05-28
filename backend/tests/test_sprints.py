"""
tests/test_sprints.py — Sprint 归集 + 燃尽 + 关键路径测试

覆盖:
- SprintTask 模型 CRUD 闭环
- snapshot_burndown 燃尽快照写入 + 更新
- compute_burndown_series 理想线 + 实际线 + 预测
- compute_critical_path 拓扑排序 + 最长路径 + 环检测
- compute_velocity_history 历史速率
- Chat Tool 集成
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.project import Project, ProjectStatus, ProjectTrack
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import (
    BurndownSnapshot,
    SprintTask,
    TaskPriority,
    TaskStatus,
)
from app.models.user import User, UserRole
from app.services.chat_tools import registry
from app.services.critical_path import compute_critical_path
from app.services.sprint_aggregator import (
    compute_burndown_series,
    compute_velocity_history,
    snapshot_burndown,
)
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


@pytest_asyncio.fixture
async def seeded(db):
    """种子:一个项目 + 一个 Sprint + 5 个任务(其中 3 个有依赖链)"""
    user = User(
        wechat_userid=f"t_sp_{uuid.uuid4().hex[:8]}",
        name="Sprint负责人",
        department="软件研发部",
        role=UserRole.manager,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    proj = Project(
        code=f"P-{uuid.uuid4().hex[:6]}",
        name="206 智能样机",
        track=ProjectTrack.software,
        status=ProjectStatus.active,
        created_by=user.id,
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)

    sprint = Sprint(
        project_id=proj.id,
        sprint_number=1,
        goal="完成 v1.0 模块联调",
        start_date=date.today() - timedelta(days=5),
        end_date=date.today() + timedelta(days=8),
        planned_story_points=20,
        status=SprintStatus.active,
        created_by=user.id,
    )
    db.add(sprint)
    await db.commit()
    await db.refresh(sprint)

    # 5 个任务,3 个依赖链:t1 → t2 → t3
    t1 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=user.id,
        title="t1 选型",
        story_points=3,
        status=TaskStatus.done,
        actual_story_points=3,
        depends_on=[],
        created_by=user.id,
    )
    t2 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=user.id,
        title="t2 实现",
        story_points=5,
        status=TaskStatus.in_progress,
        depends_on=[],
        created_by=user.id,
    )
    t3 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=user.id,
        title="t3 联调",
        story_points=8,
        status=TaskStatus.todo,
        depends_on=[],
        created_by=user.id,
    )
    t4 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=user.id,
        title="t4 独立任务",
        story_points=2,
        status=TaskStatus.todo,
        depends_on=[],
        created_by=user.id,
    )
    t5 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=user.id,
        title="t5 阻塞中",
        story_points=2,
        status=TaskStatus.blocked,
        depends_on=[],
        priority=TaskPriority.p0,
        created_by=user.id,
    )
    db.add_all([t1, t2, t3, t4, t5])
    await db.commit()
    for t in (t1, t2, t3, t4, t5):
        await db.refresh(t)

    # 依赖关系:t2 依赖 t1,t3 依赖 t2
    t2.depends_on = [str(t1.id)]
    t3.depends_on = [str(t2.id)]
    await db.commit()

    return {
        "db": db,
        "user": user,
        "proj": proj,
        "sprint": sprint,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "t4": t4,
        "t5": t5,
    }


# ════════════════════════════════════════════════════════════════
# 1. 燃尽快照
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_snapshot_basic(seeded):
    db = seeded["db"]
    snap = await snapshot_burndown(db, seeded["sprint"].id)
    await db.commit()

    # t1 done(3pt),其他未完成 → completed=3, total=20, remaining=17
    assert snap.total_points == 3 + 5 + 8 + 2 + 2  # 任务实际总和
    assert snap.completed_points == 3  # 只有 t1 done
    assert snap.remaining_points == snap.total_points - 3
    assert snap.done_count == 1
    assert snap.blocked_count == 1
    assert snap.in_progress_count == 1
    assert snap.todo_count == 2


@pytest.mark.asyncio
async def test_snapshot_idempotent_same_day(seeded):
    """同一天重复 snapshot 应更新而非新增"""
    db = seeded["db"]
    s1 = await snapshot_burndown(db, seeded["sprint"].id)
    await db.commit()
    s2 = await snapshot_burndown(db, seeded["sprint"].id)
    await db.commit()
    assert s1.id == s2.id

    all_snaps = (
        (await db.execute(select(BurndownSnapshot).where(BurndownSnapshot.sprint_id == seeded["sprint"].id)))
        .scalars()
        .all()
    )
    assert len(all_snaps) == 1


@pytest.mark.asyncio
async def test_snapshot_reflects_status_change(seeded):
    db = seeded["db"]
    await snapshot_burndown(db, seeded["sprint"].id)
    await db.commit()

    # 把 t2 改为 done,重新快照
    seeded["t2"].status = TaskStatus.done
    seeded["t2"].actual_story_points = 5
    await db.commit()

    snap = await snapshot_burndown(db, seeded["sprint"].id)
    await db.commit()
    assert snap.completed_points == 3 + 5  # t1 + t2
    assert snap.done_count == 2


# ════════════════════════════════════════════════════════════════
# 2. 燃尽序列(理想 + 实际 + 预测)
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_burndown_series_structure(seeded):
    db = seeded["db"]
    await snapshot_burndown(db, seeded["sprint"].id)
    await db.commit()
    data = await compute_burndown_series(db, seeded["sprint"].id)

    assert "sprint" in data
    assert data["total_points"] > 0
    assert len(data["ideal_line"]) >= 2
    # 理想线起点 = 总点数,终点 = 0
    assert data["ideal_line"][0]["points"] == data["total_points"]
    assert data["ideal_line"][-1]["points"] == 0
    assert len(data["actual_line"]) >= 1


@pytest.mark.asyncio
async def test_burndown_series_on_track_estimate(seeded):
    """烧得快 → on_track=True"""
    db = seeded["db"]
    # 两天的快照,模拟「快速燃尽」
    yesterday = date.today() - timedelta(days=1)
    await snapshot_burndown(db, seeded["sprint"].id, snap_date=yesterday)
    # 模拟今天又烧了一些
    seeded["t2"].status = TaskStatus.done
    seeded["t2"].actual_story_points = 5
    await db.commit()
    await snapshot_burndown(db, seeded["sprint"].id, snap_date=date.today())
    await db.commit()

    data = await compute_burndown_series(db, seeded["sprint"].id)
    est = data["today_estimate"]
    assert "burn_rate_per_day" in est
    assert "projected_end_date" in est


# ════════════════════════════════════════════════════════════════
# 3. 关键路径
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_critical_path_picks_longest_chain(seeded):
    """t1(3) → t2(5) → t3(8) 总 16pt,应是关键路径"""
    db = seeded["db"]
    result = await compute_critical_path(db, seeded["sprint"].id, persist=True)
    await db.commit()

    path_ids = result["critical_path"]
    titles = [t["title"] for t in result["tasks"] if t["id"] in set(path_ids)]
    assert "t1 选型" in titles
    assert "t2 实现" in titles
    assert "t3 联调" in titles
    assert result["critical_length"] == 3 + 5 + 8
    assert result["has_cycle"] is False

    # t4 独立任务 不在关键路径
    t4_id = str(seeded["t4"].id)
    assert t4_id not in path_ids

    # is_on_critical_path 已被回写
    await db.refresh(seeded["t3"])
    assert seeded["t3"].is_on_critical_path is True
    await db.refresh(seeded["t4"])
    assert seeded["t4"].is_on_critical_path is False


@pytest.mark.asyncio
async def test_critical_path_detects_cycle(seeded):
    """构造环 t1 → t2 → t1,应检测到 has_cycle"""
    db = seeded["db"]
    seeded["t1"].depends_on = [str(seeded["t2"].id)]
    await db.commit()
    result = await compute_critical_path(db, seeded["sprint"].id, persist=False)
    assert result["has_cycle"] is True


@pytest.mark.asyncio
async def test_critical_path_empty_sprint(db, seeded):
    """无任务的 sprint 返回空路径,不抛"""
    user = seeded["user"]
    proj = seeded["proj"]
    empty_sprint = Sprint(
        project_id=proj.id,
        sprint_number=99,
        goal="empty",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=7),
        status=SprintStatus.active,
        created_by=user.id,
    )
    db.add(empty_sprint)
    await db.commit()
    await db.refresh(empty_sprint)
    result = await compute_critical_path(db, empty_sprint.id)
    assert result["critical_path"] == []
    assert result["critical_length"] == 0


# ════════════════════════════════════════════════════════════════
# 4. 速率历史
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_velocity_history(seeded):
    db = seeded["db"]
    user = seeded["user"]
    proj = seeded["proj"]

    # 创建 2 个已完成 Sprint
    for i in range(2):
        s = Sprint(
            project_id=proj.id,
            sprint_number=10 + i,
            goal=f"s{i}",
            start_date=date.today() - timedelta(days=30 - i * 14),
            end_date=date.today() - timedelta(days=16 - i * 14),
            planned_story_points=20,
            completed_story_points=18 + i,
            status=SprintStatus.completed,
            health_score=85,
            created_by=user.id,
        )
        db.add(s)
    await db.commit()

    result = await compute_velocity_history(db, proj.id, last_n=5)
    assert result["count"] == 2
    assert result["avg_velocity"] in (18.5,)  # (18+19)/2
    # 历史按时间正序
    assert result["history"][0]["sprint_number"] == 10
    assert result["history"][1]["sprint_number"] == 11


# ════════════════════════════════════════════════════════════════
# 5. Chat Tools
# ════════════════════════════════════════════════════════════════


def test_sprint_tools_registered():
    names = set(registry.names())
    assert "sprint_status" in names
    assert "sprint_burndown" in names
    assert "critical_path" in names
    assert "project_velocity" in names


@pytest.mark.asyncio
async def test_tool_sprint_status(seeded):
    db = seeded["db"]
    result = await registry.dispatch(
        "sprint_status",
        db,
        {"project_query": seeded["proj"].code},
    )
    assert "project" in result
    assert "sprint" in result
    assert result["task_count"] == 5
    assert result["task_distribution"]["done"] == 1
    assert result["task_distribution"]["blocked"] == 1


@pytest.mark.asyncio
async def test_tool_sprint_burndown(seeded):
    db = seeded["db"]
    await snapshot_burndown(db, seeded["sprint"].id)
    await db.commit()

    result = await registry.dispatch(
        "sprint_burndown",
        db,
        {"project_query": "206"},
    )
    assert "sprint" in result
    assert result["total_points"] > 0
    assert "latest_snapshot" in result


@pytest.mark.asyncio
async def test_tool_critical_path(seeded):
    db = seeded["db"]
    result = await registry.dispatch(
        "critical_path",
        db,
        {"project_query": "206"},
    )
    assert result["critical_length_points"] == 16  # 3 + 5 + 8
    assert result["task_count_on_path"] == 3
    assert len(result["path"]) == 3


@pytest.mark.asyncio
async def test_tool_project_velocity(seeded):
    db = seeded["db"]
    user = seeded["user"]
    proj = seeded["proj"]
    # 加 1 个 completed sprint
    s = Sprint(
        project_id=proj.id,
        sprint_number=99,
        goal="历史",
        start_date=date.today() - timedelta(days=20),
        end_date=date.today() - timedelta(days=6),
        planned_story_points=15,
        completed_story_points=12,
        status=SprintStatus.completed,
        health_score=80,
        created_by=user.id,
    )
    db.add(s)
    await db.commit()

    result = await registry.dispatch(
        "project_velocity",
        db,
        {"project_query": proj.code, "last_n": 5},
    )
    assert result["count"] == 1
    assert result["avg_velocity"] == 12


@pytest.mark.asyncio
async def test_tool_sprint_status_no_project(db):
    result = await registry.dispatch(
        "sprint_status",
        db,
        {"project_query": "不存在的项目xxx"},
    )
    assert "error" in result
