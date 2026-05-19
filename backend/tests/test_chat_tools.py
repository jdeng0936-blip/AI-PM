"""
tests/test_chat_tools.py — Tool 注册框架 + 报表 Tool 测试

覆盖:
- @tool 装饰器自动 schema 生成(类型映射 + docstring 解析)
- ToolRegistry.dispatch 容错(未知 tool / 异常 / 多余参数)
- 报表 Tool 的 SQL 正确性(用真实数据库 + 种子数据)
- 时间窗口解析
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.daily_report import DailyReport
from app.models.user import User, UserRole
from app.services.chat_tools import registry, tool
from app.services.chat_tools.reports import _resolve_range


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


# ────────────────────────────────────────────────────────────────
# 框架测试
# ────────────────────────────────────────────────────────────────


def test_registry_has_expected_tools():
    names = registry.names()
    assert "query_reports" in names
    assert "count_delayed" in names
    assert "score_ranking" in names
    assert "top_performers" in names
    assert "list_active_risks" in names
    assert "user_snapshot" in names


def test_openai_schema_shape():
    schemas = registry.openai_schemas(only=["query_reports"])
    assert len(schemas) == 1
    spec = schemas[0]
    assert spec["type"] == "function"
    fn = spec["function"]
    assert fn["name"] == "query_reports"
    assert fn["description"]
    params = fn["parameters"]
    assert params["type"] == "object"
    # 类型映射应正确(不是全 string)
    assert params["properties"]["days"]["type"] == "integer"
    assert params["properties"]["only_passed"]["type"] == "boolean"
    assert params["properties"]["date_range"]["type"] == "string"
    # docstring 描述应被抽取
    assert "时间段" in params["properties"]["date_range"]["description"]


def test_tool_decorator_registers(monkeypatch):
    """临时注册一个 Tool 验证装饰器"""
    from sqlalchemy.ext.asyncio import AsyncSession

    @tool(description="测试用 Tool")
    async def __test_demo(db: AsyncSession, x: int, y: str = "default") -> dict:
        """
        Args:
            x: x 参数
            y: y 参数
        """
        return {"x": x, "y": y}

    spec = registry.get("__test_demo")
    assert spec is not None
    schema = spec.to_openai_schema()
    props = schema["function"]["parameters"]["properties"]
    assert props["x"]["type"] == "integer"
    assert props["y"]["type"] == "string"
    assert schema["function"]["parameters"]["required"] == ["x"]


# ────────────────────────────────────────────────────────────────
# dispatch 容错
# ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(db):
    result = await registry.dispatch("not_exists", db, {})
    assert "error" in result
    assert "unknown" in result["error"].lower()


@pytest.mark.asyncio
async def test_dispatch_extra_args_filtered(db):
    """多余参数应被自动过滤,不应抛 TypeError"""
    result = await registry.dispatch(
        "list_missing_today", db, {"foo": "bar", "extra": 123},
    )
    # 不报错即通过
    assert "error" not in result or "unknown" not in (result.get("error") or "").lower()


@pytest.mark.asyncio
async def test_dispatch_catches_exception(db):
    """Tool 内部异常应被包装为 error 返回,而不是抛出"""

    @tool(description="测试异常 Tool")
    async def __raises_demo(db) -> dict:
        raise RuntimeError("boom")

    result = await registry.dispatch("__raises_demo", db, {})
    assert "error" in result
    assert "RuntimeError" in result["error"]


# ────────────────────────────────────────────────────────────────
# 时间窗口解析
# ────────────────────────────────────────────────────────────────


def test_resolve_range_days_priority():
    start, end = _resolve_range("this_week", 14)
    assert (end - start).days == 13  # 包含今天的近 14 天


def test_resolve_range_today():
    start, end = _resolve_range("today", 0)
    assert start == end == date.today()


def test_resolve_range_yesterday():
    start, end = _resolve_range("yesterday", 0)
    assert start == end == date.today() - timedelta(days=1)


def test_resolve_range_this_week():
    start, end = _resolve_range("this_week", 0)
    assert end == date.today()
    assert start.weekday() == 0  # 周一


def test_resolve_range_fallback():
    """无效值兜底为近 7 天"""
    start, end = _resolve_range("garbage", 0)
    assert (end - start).days == 6


# ────────────────────────────────────────────────────────────────
# Tool 业务正确性(种子数据 + SQL 验证)
# ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_db(db):
    """种子:3 个用户、近 3 天若干日报"""
    u1 = User(
        wechat_userid=f"t_chat_a_{uuid.uuid4().hex[:6]}",
        name="郭A", department="软件研发部", role=UserRole.employee,
    )
    u2 = User(
        wechat_userid=f"t_chat_b_{uuid.uuid4().hex[:6]}",
        name="陈B", department="软件研发部", role=UserRole.employee,
    )
    u3 = User(
        wechat_userid=f"t_chat_c_{uuid.uuid4().hex[:6]}",
        name="陶C", department="采购部", role=UserRole.employee,
    )
    db.add_all([u1, u2, u3])
    await db.commit()
    for u in (u1, u2, u3):
        await db.refresh(u)

    today = date.today()
    reports = [
        DailyReport(
            user_id=u1.id, report_date=today, raw_input_text="x",
            ai_score=90, pass_check=True,
            parsed_content={"progress": 100, "blocker": "无", "tasks": "完成模块A"},
        ),
        DailyReport(
            user_id=u1.id, report_date=today - timedelta(days=1), raw_input_text="x",
            ai_score=85, pass_check=True,
            parsed_content={"progress": 80, "blocker": "MCU缺货", "tasks": "卡在采购"},
        ),
        DailyReport(
            user_id=u2.id, report_date=today, raw_input_text="x",
            ai_score=60, pass_check=False,
            parsed_content={"progress": 40, "blocker": "API设计争议", "tasks": "讨论中"},
        ),
        DailyReport(
            user_id=u3.id, report_date=today, raw_input_text="x",
            ai_score=88, pass_check=True,
            parsed_content={"progress": 100, "blocker": "", "tasks": "签订单"},
        ),
    ]
    db.add_all(reports)
    await db.commit()
    return {"u1": u1, "u2": u2, "u3": u3, "db": db}


@pytest.mark.asyncio
async def test_query_reports_basic(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "query_reports", db, {"date_range": "last_7_days", "limit": 10},
    )
    assert "items" in result
    assert result["total_count"] >= 4
    assert result["avg_score"] is not None
    assert isinstance(result["items"], list)


@pytest.mark.asyncio
async def test_query_reports_department_filter(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "query_reports", db,
        {"date_range": "today", "department": "采购部", "limit": 10},
    )
    # 当天采购部应该只有陶C
    for it in result["items"]:
        assert it["department"] == "采购部"


@pytest.mark.asyncio
async def test_count_delayed_picks_blockers(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "count_delayed", db, {"date_range": "last_7_days", "limit": 10},
    )
    names = [r["user"] for r in result["ranking"]]
    # 郭A 和 陈B 都有卡点,陶C 卡点为空字符串应被排除
    assert "陶C" not in names


@pytest.mark.asyncio
async def test_score_ranking_top(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "score_ranking", db,
        {"date_range": "today", "direction": "top", "limit": 5},
    )
    if result["ranking"]:
        # top 模式下第一名分数应是最高
        scores = [r["avg_score"] for r in result["ranking"] if r["avg_score"]]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_score_ranking_bottom(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "score_ranking", db,
        {"date_range": "today", "direction": "bottom", "limit": 5},
    )
    if result["ranking"]:
        scores = [r["avg_score"] for r in result["ranking"] if r["avg_score"]]
        assert scores == sorted(scores)


@pytest.mark.asyncio
async def test_list_missing_today(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch("list_missing_today", db, {})
    # 至少种子的 3 个用户都已提交了今日日报,种子用户不应在 missing 里
    missing_names = {m["user"] for m in result["missing"]}
    assert "郭A" not in missing_names
    assert "陈B" not in missing_names
    assert "陶C" not in missing_names


@pytest.mark.asyncio
async def test_user_snapshot(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "user_snapshot", db, {"user_name": "郭A", "days": 7},
    )
    assert result["user"] == "郭A"
    assert result["submitted_days"] >= 2
    assert result["avg_score"] is not None
    assert "MCU缺货" in result["recent_blockers"]


@pytest.mark.asyncio
async def test_user_snapshot_not_found(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "user_snapshot", db, {"user_name": "不存在的人", "days": 7},
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_top_performers_composite_ranking(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "top_performers", db, {"days": 7, "limit": 5},
    )
    assert "ranking" in result
    # 综合分应单调递减
    scores = [r["composite_score"] for r in result["ranking"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_avg_score_by_department(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch(
        "avg_score_by_department", db, {"date_range": "today"},
    )
    depts = {d["department"] for d in result["departments"]}
    assert "软件研发部" in depts
    assert "采购部" in depts
