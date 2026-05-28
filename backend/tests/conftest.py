"""
tests/conftest.py — pytest 全局 Fixtures (Rule 01-Stack-Backend)

规则要求：
  - 统一使用 pytest + pytest-asyncio
  - 路由测试用 httpx.AsyncClient
  - 数据库测试通过 dependency_overrides 替换回滚 session
"""

import asyncio
import os
from importlib import import_module
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from tests._db_url import derive_test_database_url
from tests._isolation import clean_external_settings

app = cast(Any, import_module("app.main").app)

# ── 使用独立测试数据库（生产数据库名追加 _test）──────────────────
# CI 显式传 DATABASE_URL_TEST;本地未配置时沿用历史规则。
# T-1102 议题 C:用 derive_test_database_url 替代 str.replace,
# 防御 DB 名非 `aipm_db` 时硬编码 replace 失效落到生产 URL 的风险。
TEST_DATABASE_URL = os.getenv("DATABASE_URL_TEST") or derive_test_database_url(settings.database_url)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture(scope="session")
def event_loop():
    """为整个测试会话创建一个事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """
    测试会话开始时创建所有表，结束后清理。

    V2.5 Stage 1 P1 #6:测试库不可达时(本地没起 PG / CI 没配测试库)
    pytest.skip 整个 session,而不是让所有依赖 fixture 的测试报 ConnectionError。
    无 DB 依赖的单元测试(如 test_models_init / test_distributed_lock 等 mock
    驱动)仍能跑,因为它们不 request db_session/client fixture。
    """
    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        message = (
            f"测试数据库不可达 ({TEST_DATABASE_URL.rsplit('@', 1)[-1]}): {type(e).__name__}: "
            f"{str(e)[:120]}。请先 `createdb aipm_db_test` 或设置 DATABASE_URL_TEST。"
        )
        if os.getenv("CI_REQUIRE_TEST_DB") == "1":
            pytest.exit(message, returncode=1)
        pytest.skip(message, allow_module_level=True)
    yield
    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception:
        pass  # 清理失败不影响测试结论
    await test_engine.dispose()


@pytest.fixture(autouse=True)
def _isolation_external_settings(monkeypatch):
    """
    T-1103 议题 A:全局测试隔离 — 清空所有外部敏感 settings(wechat / dingtalk /
    smtp / asr / oss / new_api / sentry / erp_webhook),让任何 test 不依赖
    跑测试者本机 .env 状态。

    autouse=True 让所有 test case 默认享受 isolation。test 内若需要测「已配置」
    分支,自行 monkeypatch.setattr 覆盖(later setattr wins)。
    """
    clean_external_settings(monkeypatch)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    每个测试用例独立的数据库 session，自动回滚。
    """
    async with TestSessionLocal() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    httpx.AsyncClient + dependency_overrides（注入测试 session）
    """

    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
