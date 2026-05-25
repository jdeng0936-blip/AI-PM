"""
tests/test_capacity.py — 资源水位测试

覆盖:
- classify_level 等级判定
- compute_user_capacity 单人计算(含状态折减 + velocity 调整)
- snapshot_sprint_capacity 全员快照 + 幂等
- find_overloaded / find_underutilized
- suggest_rebalance 跨人员任务调配
- department_capacity_summary 部门聚合
- Chat Tools 集成
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
from app.models.capacity import CapacityLevel, CapacitySnapshot
from app.models.project import Project, ProjectStatus, ProjectTrack
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import SprintTask, TaskPriority, TaskStatus
from app.models.user import User, UserRole, UserStatus
from app.services import capacity_engine
from app.services.capacity_engine import (
    classify_level,
    compute_user_capacity,
    department_capacity_summary,
    find_overloaded,
    find_underutilized,
    snapshot_sprint_capacity,
    suggest_rebalance,
)
from app.services.chat_tools import registry

TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")


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
    """种子:
    - 3 个用户:over_user(过载) / idle_user(闲置) / normal_user(健康)
    - 1 个项目 + 1 active Sprint
    - 任务分配:over=15pt(超出容量 8),idle=1pt,normal=5pt
    """
    over_user = User(
        wechat_userid=f"t_over_{uuid.uuid4().hex[:6]}",
        name="过载工",
        department="软件研发部",
        role=UserRole.employee,
        story_points_capacity=8,
    )
    idle_user = User(
        wechat_userid=f"t_idle_{uuid.uuid4().hex[:6]}",
        name="闲置工",
        department="软件研发部",
        role=UserRole.employee,
        story_points_capacity=8,
    )
    normal_user = User(
        wechat_userid=f"t_norm_{uuid.uuid4().hex[:6]}",
        name="健康工",
        department="采购部",
        role=UserRole.employee,
        story_points_capacity=8,
    )
    db.add_all([over_user, idle_user, normal_user])
    await db.commit()
    for u in (over_user, idle_user, normal_user):
        await db.refresh(u)

    proj = Project(
        code=f"P-{uuid.uuid4().hex[:6]}",
        name="水位测试",
        track=ProjectTrack.software,
        status=ProjectStatus.active,
        created_by=over_user.id,
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)

    sprint = Sprint(
        project_id=proj.id,
        sprint_number=1,
        goal="capacity test",
        start_date=date.today() - timedelta(days=2),
        end_date=date.today() + timedelta(days=11),
        planned_story_points=30,
        status=SprintStatus.active,
        created_by=over_user.id,
    )
    db.add(sprint)
    await db.commit()
    await db.refresh(sprint)

    # over: 3 个任务 5+5+5=15pt(其中 1 个 todo + 非关键路径,可调配)
    t1 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=over_user.id,
        title="ov_t1",
        story_points=5,
        status=TaskStatus.in_progress,
        priority=TaskPriority.p1,
        is_on_critical_path=True,
        created_by=over_user.id,
    )
    t2 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=over_user.id,
        title="ov_t2",
        story_points=5,
        status=TaskStatus.todo,
        priority=TaskPriority.p2,
        is_on_critical_path=False,
        created_by=over_user.id,
    )
    t3 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=over_user.id,
        title="ov_t3",
        story_points=5,
        status=TaskStatus.todo,
        priority=TaskPriority.p3,
        is_on_critical_path=False,
        created_by=over_user.id,
    )
    # idle: 1 个 1pt 任务
    t4 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=idle_user.id,
        title="id_t1",
        story_points=1,
        status=TaskStatus.todo,
        created_by=idle_user.id,
    )
    # normal: 5pt(健康)
    t5 = SprintTask(
        sprint_id=sprint.id,
        assignee_id=normal_user.id,
        title="nm_t1",
        story_points=5,
        status=TaskStatus.in_progress,
        created_by=normal_user.id,
    )
    db.add_all([t1, t2, t3, t4, t5])
    await db.commit()

    return {
        "db": db,
        "proj": proj,
        "sprint": sprint,
        "over_user": over_user,
        "idle_user": idle_user,
        "normal_user": normal_user,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "t4": t4,
        "t5": t5,
    }


# ════════════════════════════════════════════════════════════════
# 1. 等级判定
# ════════════════════════════════════════════════════════════════


def test_classify_level_boundaries():
    assert classify_level(0.0) == CapacityLevel.idle
    assert classify_level(0.29) == CapacityLevel.idle
    assert classify_level(0.3) == CapacityLevel.healthy
    assert classify_level(0.79) == CapacityLevel.healthy
    assert classify_level(0.8) == CapacityLevel.high
    assert classify_level(0.99) == CapacityLevel.high
    assert classify_level(1.0) == CapacityLevel.overload
    assert classify_level(2.0) == CapacityLevel.overload


# ════════════════════════════════════════════════════════════════
# 2. 单人计算
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_compute_user_capacity_overload(seeded, monkeypatch):
    """over_user: 15pt 分配 / 8pt 容量 = 187%"""
    db = seeded["db"]

    # 屏蔽 velocity 调整,避免历史样本影响判定
    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    m = await compute_user_capacity(db, seeded["over_user"], seeded["sprint"])
    assert m["allocated_points"] == 15
    assert m["effective_capacity"] == 8
    assert m["utilization"] > 1.0
    assert m["level"] == "overload"
    assert m["active_task_count"] == 3
    assert m["critical_path_task_count"] == 1


@pytest.mark.asyncio
async def test_compute_user_capacity_idle(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    m = await compute_user_capacity(db, seeded["idle_user"], seeded["sprint"])
    assert m["allocated_points"] == 1
    assert m["utilization"] < 0.3
    assert m["level"] == "idle"


@pytest.mark.asyncio
async def test_compute_user_capacity_healthy(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    m = await compute_user_capacity(db, seeded["normal_user"], seeded["sprint"])
    # 5/8 = 62.5%
    assert 0.3 <= m["utilization"] < 0.8
    assert m["level"] == "healthy"


@pytest.mark.asyncio
async def test_compute_user_capacity_on_leave(seeded, monkeypatch):
    """休假状态:effective_capacity 应为 0,utilization=2.0(极度过载)"""
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    seeded["normal_user"].status = UserStatus.on_leave
    await db.commit()
    m = await compute_user_capacity(db, seeded["normal_user"], seeded["sprint"])
    assert m["effective_capacity"] == 0
    assert m["status_factor"] == 0.0
    assert m["level"] == "overload"  # 有任务但容量 0


@pytest.mark.asyncio
async def test_compute_user_capacity_on_travel(seeded, monkeypatch):
    """出差状态:容量 ×0.5"""
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    seeded["normal_user"].status = UserStatus.on_travel
    await db.commit()
    m = await compute_user_capacity(db, seeded["normal_user"], seeded["sprint"])
    assert m["effective_capacity"] == 4  # 8 * 0.5
    # 5/4 = 125% → overload
    assert m["level"] == "overload"


# ════════════════════════════════════════════════════════════════
# 3. 快照 + 幂等
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_snapshot_writes_all_assignees(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    rows = await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()
    assert len(rows) == 3  # 3 个 assignee

    saved = (
        (await db.execute(select(CapacitySnapshot).where(CapacitySnapshot.sprint_id == seeded["sprint"].id)))
        .scalars()
        .all()
    )
    assert len(saved) == 3


@pytest.mark.asyncio
async def test_snapshot_idempotent(seeded, monkeypatch):
    """重复 snapshot 应更新而非新增"""
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()
    # 第二次
    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    rows = (
        (await db.execute(select(CapacitySnapshot).where(CapacitySnapshot.sprint_id == seeded["sprint"].id)))
        .scalars()
        .all()
    )
    assert len(rows) == 3  # 没有重复


@pytest.mark.asyncio
async def test_snapshot_reflects_task_status_change(seeded, monkeypatch):
    """改任务状态后重新 snapshot,allocated 应减少"""
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    # 把 over 的 t3 标记 done
    seeded["t3"].status = TaskStatus.done
    seeded["t3"].actual_story_points = 5
    await db.commit()

    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    snap = (
        await db.execute(
            select(CapacitySnapshot).where(
                CapacitySnapshot.user_id == seeded["over_user"].id,
                CapacitySnapshot.sprint_id == seeded["sprint"].id,
            )
        )
    ).scalar_one()
    # allocated 应从 15 减到 10(t3 完成)
    assert snap.allocated_points == 10
    assert snap.completed_points == 5


# ════════════════════════════════════════════════════════════════
# 4. 查询
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_find_overloaded(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)
    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    items = await find_overloaded(db)
    names = [x["user_name"] for x in items]
    assert "过载工" in names
    assert "健康工" not in names
    assert "闲置工" not in names


@pytest.mark.asyncio
async def test_find_underutilized(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)
    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    items = await find_underutilized(db)
    names = [x["user_name"] for x in items]
    assert "闲置工" in names
    assert "过载工" not in names


# ════════════════════════════════════════════════════════════════
# 5. 调配建议
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rebalance_picks_non_critical_todo(seeded, monkeypatch):
    """调配只移动 todo + 非关键路径任务"""
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)
    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    result = await suggest_rebalance(db, seeded["sprint"].id)
    assert len(result["overloaded"]) >= 1
    assert len(result["idle"]) >= 1
    # 应该有调配建议(因为 over 有 t2/t3 都是 todo+非关键)
    assert len(result["moves"]) >= 1
    for m in result["moves"]:
        # 不应推荐 t1(关键路径 + in_progress)
        assert m["title"] != "ov_t1"


@pytest.mark.asyncio
async def test_rebalance_prefers_same_department(seeded, monkeypatch):
    """同部门 idle 优先匹配:idle_user 与 over_user 都在软件研发部"""
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)
    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    result = await suggest_rebalance(db, seeded["sprint"].id)
    if result["moves"]:
        # 至少首条应优先转给 idle_user(同部门)
        first = result["moves"][0]
        assert first["to_user"] == "闲置工"
        assert first["department_match"] is True


@pytest.mark.asyncio
async def test_rebalance_empty_when_no_overload(db):
    """无过载时返回空 moves"""
    result = await suggest_rebalance(db, uuid.uuid4())  # 不存在的 sprint
    assert result["moves"] == []


# ════════════════════════════════════════════════════════════════
# 6. 部门聚合
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_department_summary(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)
    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    result = await department_capacity_summary(db, sprint_id=seeded["sprint"].id)
    depts = {d["department"] for d in result["departments"]}
    assert "软件研发部" in depts
    assert "采购部" in depts
    # 软件研发部 = 过载工 15pt + 闲置工 1pt = 16pt / (8+8)pt = 100% overload
    sw = next(d for d in result["departments"] if d["department"] == "软件研发部")
    assert sw["total_allocated"] == 16
    assert sw["total_capacity"] == 16
    assert sw["utilization"] == 1.0
    assert sw["level"] == "overload"


# ════════════════════════════════════════════════════════════════
# 7. Chat Tools
# ════════════════════════════════════════════════════════════════


def test_capacity_tools_registered():
    names = set(registry.names())
    assert "workload_status" in names
    assert "list_overloaded_members" in names
    assert "list_underutilized_members" in names
    assert "rebalance_suggestion" in names
    assert "department_workload" in names


@pytest.mark.asyncio
async def test_tool_workload_status(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)

    result = await registry.dispatch(
        "workload_status",
        db,
        {"project_query": seeded["proj"].code},
    )
    assert result["member_count"] == 3
    assert result["distribution"]["overload"] >= 1
    assert result["distribution"]["idle"] >= 1


@pytest.mark.asyncio
async def test_tool_rebalance_suggestion(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_v(*a, **kw):
        return 1.0

    monkeypatch.setattr(capacity_engine, "compute_velocity_factor", fake_v)
    await snapshot_sprint_capacity(db, seeded["sprint"].id)
    await db.commit()

    result = await registry.dispatch(
        "rebalance_suggestion",
        db,
        {"project_query": seeded["proj"].code},
    )
    assert result["overloaded_count"] >= 1
    assert result["move_count"] >= 1


@pytest.mark.asyncio
async def test_tool_workload_status_no_project(db):
    result = await registry.dispatch(
        "workload_status",
        db,
        {"project_query": "不存在xxx"},
    )
    assert "error" in result
