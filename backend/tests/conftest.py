"""
tests/conftest.py — pytest 全局 Fixtures (Rule 01-Stack-Backend)

规则要求：
  - 统一使用 pytest + pytest-asyncio
  - 路由测试用 httpx.AsyncClient
  - 数据库测试通过 dependency_overrides 替换回滚 session
"""
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.main import app
from app.config import settings


# ── 使用独立测试数据库（生产数据库名追加 _test）──────────────────
TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, expire_on_commit=False, class_=AsyncSession
)


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
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


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
