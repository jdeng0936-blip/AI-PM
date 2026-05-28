"""
tests/test_notifications.py — 通知服务测试

覆盖:
- 模板渲染(占位符 + 缺失字段兜底)— 纯函数,无需 DB
- 渠道未配置时优雅 skip — 需 DB
- notifications 表落库 — 需 DB
- 群推渠道无 user 参数 — 需 DB

注:为绕开 conftest.py 中 session.begin() 与 asyncpg 的兼容性问题,
DB 类测试自管会话,显式 commit/rollback。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
)
from app.models.user import User, UserRole
from app.services.notification_service import notify, render_template
from tests._db_url import derive_test_database_url

# ────────────────────────────────────────────────────────────────
# 纯函数测试:模板渲染(不依赖 DB)
# ────────────────────────────────────────────────────────────────


def test_render_report_rejected():
    title, body = render_template(
        NotificationTemplate.report_rejected,
        {"name": "郭震", "reason": "缺少版本号", "guidance": "请补充 v2.1"},
    )
    assert title == "日报需要补充"
    assert "郭震" in body
    assert "缺少版本号" in body
    assert "请补充 v2.1" in body


def test_render_missing_field_fallback():
    """缺少占位符字段时应返回空串,不抛异常"""
    title, body = render_template(
        NotificationTemplate.report_passed,
        {"name": "郭震"},  # 缺少 score/comment
    )
    assert title == "日报已收录"
    assert "郭震" in body
    assert "{score}" not in body
    assert "{comment}" not in body


def test_render_risk_alert():
    title, body = render_template(
        NotificationTemplate.risk_alert,
        {
            "name": "张维",
            "department": "软件研发部",
            "alert_type": "blocker",
            "description": "MCU 芯片缺货",
            "days_unresolved": 3,
        },
    )
    assert "风险预警" in title
    assert "张维" in body
    assert "MCU 芯片缺货" in body
    assert "3 天" in body


def test_render_all_templates_no_crash():
    """所有模板传空 context 都不应抛异常"""
    for tpl in NotificationTemplate:
        title, body = render_template(tpl, {})
        assert isinstance(title, str)
        assert isinstance(body, str)


# ────────────────────────────────────────────────────────────────
# DB 测试:自管会话(绕开 conftest 的 begin() 包裹)
# ────────────────────────────────────────────────────────────────


TEST_DATABASE_URL = derive_test_database_url(settings.database_url)


@pytest_asyncio.fixture
async def isolated_db():
    """为每个测试创建独立 engine + session,测试结束清理。"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def _clean_notification_settings(monkeypatch):
    """
    T-1102 议题 A:测试自治 — 主动清空所有通知通道 settings,
    让 `test_notify_unconfigured_channels_skipped` 等 case 不依赖
    跑测试者本机 `.env` 状态(否则本地配了真实 Webhook 会导致 notify
    走真实请求 → 4xx/5xx → assert 失败)。

    autouse=True 让本模块所有 DB 测试统一享受 isolation,纯 render 测试
    用不上但无副作用(monkeypatch 在 test 结束自动还原)。
    """
    monkeypatch.setattr(settings, "wechat_corp_id", "", raising=False)
    monkeypatch.setattr(settings, "wechat_corp_secret", "", raising=False)
    monkeypatch.setattr(settings, "wechat_agent_id", "", raising=False)
    monkeypatch.setattr(settings, "wechat_bot_webhook", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_bot_webhook", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_bot_secret", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_app_key", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_app_secret", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_agent_id", "", raising=False)
    monkeypatch.setattr(settings, "smtp_server", "", raising=False)
    monkeypatch.setattr(settings, "smtp_user", "", raising=False)
    monkeypatch.setattr(settings, "smtp_password", "", raising=False)
    monkeypatch.setattr(settings, "smtp_from_email", "", raising=False)


@pytest.mark.asyncio
async def test_notify_in_app_only(isolated_db):
    """站内信渠道:始终标记为 sent + 落库"""
    user = User(
        wechat_userid=f"test_inapp_{uuid.uuid4().hex[:8]}",
        name="测试员工A",
        department="测试部",
        role=UserRole.employee,
    )
    isolated_db.add(user)
    await isolated_db.commit()
    await isolated_db.refresh(user)

    records = await notify(
        isolated_db,
        template=NotificationTemplate.report_passed,
        context={"name": user.name, "score": 88, "comment": "Good"},
        channels=[NotificationChannel.in_app],
        user=user,
    )
    await isolated_db.commit()

    assert len(records) == 1
    assert records[0].status == NotificationStatus.sent
    assert records[0].channel == NotificationChannel.in_app
    assert records[0].sent_at is not None
    assert "88" in records[0].body


@pytest.mark.asyncio
async def test_notify_unconfigured_channels_skipped(isolated_db):
    """企微/钉钉未配置时应 skipped,不报错"""
    user = User(
        wechat_userid=f"test_skip_{uuid.uuid4().hex[:8]}",
        name="测试员工B",
        department="测试部",
        role=UserRole.employee,
    )
    isolated_db.add(user)
    await isolated_db.commit()
    await isolated_db.refresh(user)

    records = await notify(
        isolated_db,
        template=NotificationTemplate.report_rejected,
        context={"name": user.name, "reason": "x", "guidance": "y"},
        channels=[
            NotificationChannel.wechat,
            NotificationChannel.dingtalk,
            NotificationChannel.wechat_bot,
            NotificationChannel.dingtalk_bot,
        ],
        user=user,
    )
    await isolated_db.commit()

    assert len(records) == 4
    # 未配置渠道 → skipped;配置了但值是 placeholder/无效 → failed。
    # 两种都是「优雅失败」的可接受行为,不应抛异常或污染主流程。
    for r in records:
        assert r.status in (NotificationStatus.skipped, NotificationStatus.failed)
        assert r.error_message  # 必须有错误信息


@pytest.mark.asyncio
async def test_notify_persists_history(isolated_db):
    """notify() 应写入 notifications 表,可被查询"""
    user = User(
        wechat_userid=f"test_persist_{uuid.uuid4().hex[:8]}",
        name="测试员工C",
        department="测试部",
        role=UserRole.employee,
    )
    isolated_db.add(user)
    await isolated_db.commit()
    await isolated_db.refresh(user)

    await notify(
        isolated_db,
        template=NotificationTemplate.report_passed,
        context={"name": user.name, "score": 95, "comment": "Excellent"},
        channels=[NotificationChannel.in_app],
        user=user,
        related_type="test",
        related_id="abc-123",
    )
    await isolated_db.commit()

    rows = (await isolated_db.execute(select(Notification).where(Notification.user_id == user.id))).scalars().all()

    assert len(rows) >= 1
    latest = rows[-1]
    assert latest.template == NotificationTemplate.report_passed
    assert latest.related_type == "test"
    assert latest.related_id == "abc-123"
    assert latest.context["score"] == 95


@pytest.mark.asyncio
async def test_notify_no_user_for_bot_channels(isolated_db):
    """群机器人渠道无需 user 参数(群推场景)"""
    records = await notify(
        isolated_db,
        template=NotificationTemplate.daily_briefing,
        context={
            "date": "2026-05-18",
            "expected": 10,
            "submitted": 8,
            "missing": 2,
            "avg_score": 82,
            "risk_count": 1,
            "summary": "总体平稳",
        },
        channels=[NotificationChannel.wechat_bot, NotificationChannel.dingtalk_bot],
        user=None,
    )
    await isolated_db.commit()

    assert len(records) == 2
    for r in records:
        assert r.status in (NotificationStatus.skipped, NotificationStatus.sent)
        assert r.user_id is None
