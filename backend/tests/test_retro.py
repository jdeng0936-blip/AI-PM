"""
tests/test_retro.py — AI 复盘服务测试

不调用真实 LLM,所有 _call_llm 走 monkeypatch。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.daily_report import DailyReport
from app.models.knowledge import KnowledgeCategory, KnowledgeItem, RetroScope
from app.models.okr import (
    KeyResult,
    Objective,
    OKRCycle,
    OKRCycleType,
    OKRStatus,
)
from app.models.risk_alert import RiskAlert
from app.models.user import User, UserRole
from app.services import retro
from app.services.chat_tools import registry
from app.services.retro import collectors, generator
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
    """种子:一个完整的小型 OKR 周期 + 几份日报 + 一个风险"""
    user = User(
        wechat_userid=f"t_retro_{uuid.uuid4().hex[:8]}",
        name="复盘负责人",
        department="软件研发部",
        role=UserRole.manager,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    today = date.today()
    cycle = OKRCycle(
        name="2026Q1",
        cycle_type=OKRCycleType.quarterly,
        start_date=today - timedelta(days=90),
        end_date=today - timedelta(days=1),
        status=OKRStatus.active,
        created_by=user.id,
    )
    db.add(cycle)
    await db.commit()
    await db.refresh(cycle)

    obj = Objective(
        cycle_id=cycle.id,
        owner_id=user.id,
        title="提升 AI 推理效率",
        weight=1.0,
        progress=70.0,
        status=OKRStatus.active,
        created_by=user.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)

    kr = KeyResult(
        objective_id=obj.id,
        owner_id=user.id,
        title="推理延迟降至 500ms",
        target_value=500,
        current_value=450,
        unit="ms",
        confidence=0.9,
        created_by=user.id,
    )
    db.add(kr)
    await db.commit()
    await db.refresh(kr)

    # 几份日报
    for i in range(3):
        db.add(
            DailyReport(
                user_id=user.id,
                report_date=today - timedelta(days=i + 1),
                raw_input_text=f"day{i}",
                ai_score=80 + i,
                pass_check=True,
                parsed_content={"tasks": f"任务{i}", "progress": 60 + i * 10, "blocker": ""},
            )
        )
    await db.commit()

    # 一个风险
    risk_report = (await db.execute(select(DailyReport).where(DailyReport.user_id == user.id).limit(1))).scalar_one()
    risk = RiskAlert(
        report_id=risk_report.id,
        user_id=user.id,
        alert_type="blocker",
        description="GPU 资源不足",
        status="resolved",
        days_unresolved=4,
        resolved_at=datetime.now(timezone.utc),
    )
    db.add(risk)
    await db.commit()
    await db.refresh(risk)

    return {"db": db, "user": user, "cycle": cycle, "obj": obj, "kr": kr, "risk": risk}


# ════════════════════════════════════════════════════════════════
# 1. Collectors
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_collect_okr_cycle(seeded):
    db = seeded["db"]
    data = await collectors.collect_okr_cycle(db, seeded["cycle"].id)
    assert "cycle" in data
    assert data["cycle"]["name"] == "2026Q1"
    assert data["kr_count"] == 1
    assert len(data["objectives"]) == 1
    assert data["objectives"][0]["title"] == "提升 AI 推理效率"
    assert "period_basics" in data


@pytest.mark.asyncio
async def test_collect_okr_cycle_missing(db):
    data = await collectors.collect_okr_cycle(db, uuid.uuid4())
    assert "error" in data


@pytest.mark.asyncio
async def test_collect_monthly(seeded):
    db = seeded["db"]
    today = date.today()
    data = await collectors.collect_monthly(db, today.year, today.month)
    assert "month" in data
    assert "period_basics" in data
    assert isinstance(data["new_projects"], list)


@pytest.mark.asyncio
async def test_collect_incident(seeded):
    db = seeded["db"]
    data = await collectors.collect_incident(db, seeded["risk"].id)
    assert "incident" in data
    assert data["incident"]["type"] == "blocker"
    assert data["incident"]["status"] == "resolved"


# ════════════════════════════════════════════════════════════════
# 2. Generator(mock LLM)
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_okr_cycle_persists(seeded, monkeypatch):
    db = seeded["db"]

    async def fake_call(prompt: str) -> str:
        return "## 周期概览\n本周期目标达成情况良好。\n\n## 经验提炼\n- 经验 1\n- 经验 2\n- 经验 3"

    monkeypatch.setattr(generator, "_call_llm", fake_call)

    result = await retro.generate_retrospective(
        db,
        scope="okr_cycle",
        target_id=str(seeded["cycle"].id),
        actor_id=seeded["user"].id,
    )
    await db.commit()

    assert result.scope == "okr_cycle"
    assert result.title.startswith("OKR 周期复盘")
    assert "经验提炼" in result.markdown
    assert result.knowledge_item_id is not None

    # 沉淀到知识库
    item = await db.get(KnowledgeItem, uuid.UUID(result.knowledge_item_id))
    assert item is not None
    assert item.category == KnowledgeCategory.RETROSPECTIVE
    assert RetroScope.OKR_CYCLE in (item.tags or "")
    assert item.source_type == "ai_retrospective"
    assert item.source_id == str(seeded["cycle"].id)


@pytest.mark.asyncio
async def test_generate_invalid_scope(db):
    with pytest.raises(ValueError):
        await retro.generate_retrospective(db, scope="not_a_scope")


@pytest.mark.asyncio
async def test_generate_okr_cycle_missing_target(db):
    with pytest.raises(ValueError):
        await retro.generate_retrospective(db, scope="okr_cycle")


@pytest.mark.asyncio
async def test_generate_safe_swallows_exception(db, monkeypatch):
    """generate_retrospective_safe 即使 LLM 抛异常也不应让调用方挂"""

    async def boom(prompt: str) -> str:
        raise RuntimeError("LLM 网关挂了")

    monkeypatch.setattr(generator, "_call_llm", boom)

    result = await retro.generate_retrospective_safe(
        db,
        scope="monthly",
        year=2026,
        month=5,
    )
    assert result is None


@pytest.mark.asyncio
async def test_generate_monthly(seeded, monkeypatch):
    db = seeded["db"]

    async def fake(p):
        return "## 月度概览\n月度报告内容"

    monkeypatch.setattr(generator, "_call_llm", fake)

    today = date.today()
    result = await retro.generate_retrospective(
        db,
        scope="monthly",
        year=today.year,
        month=today.month,
    )
    await db.commit()

    assert result.scope == "monthly"
    assert str(today.year) in result.title
    assert result.knowledge_item_id


@pytest.mark.asyncio
async def test_generate_incident(seeded, monkeypatch):
    db = seeded["db"]

    async def fake(p):
        return "## 事件经过\n事故复盘内容"

    monkeypatch.setattr(generator, "_call_llm", fake)

    result = await retro.generate_retrospective(
        db,
        scope="incident",
        incident_id=str(seeded["risk"].id),
    )
    await db.commit()

    assert result.scope == "incident"
    assert result.knowledge_item_id


# ════════════════════════════════════════════════════════════════
# 3. Chat Tools
# ════════════════════════════════════════════════════════════════


def test_retro_tools_registered():
    names = set(registry.names())
    assert "search_retros" in names
    assert "list_recent_retros" in names
    assert "get_retro" in names


@pytest.mark.asyncio
async def test_tool_search_retros(seeded, monkeypatch):
    db = seeded["db"]

    async def fake(p):
        return "复盘内容"

    monkeypatch.setattr(generator, "_call_llm", fake)
    await retro.generate_retrospective(
        db,
        scope="okr_cycle",
        target_id=str(seeded["cycle"].id),
    )
    await db.commit()

    result = await registry.dispatch("search_retros", db, {"keyword": "2026Q1"})
    assert result["count"] >= 1
    assert any("2026Q1" in it["title"] for it in result["items"])


@pytest.mark.asyncio
async def test_tool_list_recent_retros_filter(seeded, monkeypatch):
    db = seeded["db"]

    async def fake(p):
        return "x"

    monkeypatch.setattr(generator, "_call_llm", fake)
    await retro.generate_retrospective(
        db,
        scope="okr_cycle",
        target_id=str(seeded["cycle"].id),
    )
    await db.commit()

    result = await registry.dispatch(
        "list_recent_retros",
        db,
        {"scope": "okr_cycle", "limit": 5},
    )
    assert "items" in result
    assert all("okr_cycle" in (it["tags"] or "") for it in result["items"])


@pytest.mark.asyncio
async def test_tool_list_recent_retros_invalid_scope(db):
    result = await registry.dispatch(
        "list_recent_retros",
        db,
        {"scope": "not_a_scope"},
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_get_retro_full_content(seeded, monkeypatch):
    db = seeded["db"]

    async def fake(p):
        return "## 完整正文\n详情内容"

    monkeypatch.setattr(generator, "_call_llm", fake)
    res = await retro.generate_retrospective(
        db,
        scope="okr_cycle",
        target_id=str(seeded["cycle"].id),
    )
    await db.commit()

    result = await registry.dispatch("get_retro", db, {"retro_id": res.knowledge_item_id})
    assert "content" in result
    assert "完整正文" in result["content"]


@pytest.mark.asyncio
async def test_tool_get_retro_invalid_uuid(db):
    result = await registry.dispatch("get_retro", db, {"retro_id": "not-a-uuid"})
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_get_retro_not_found(db):
    result = await registry.dispatch("get_retro", db, {"retro_id": str(uuid.uuid4())})
    assert "error" in result
