"""
app/database.py — 异步数据库连接池（AsyncSession + asyncpg）
使用 SQLAlchemy 2.0 纯异步模式，支持 PostgreSQL 15+。
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# 连接引擎（pool_size=10 适合中小规模并发，生产可按需调整）
engine = create_async_engine(
    settings.database_url,
    echo=False,          # 生产关闭 SQL 日志，调试时改为 True
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # 心跳检测，防止空闲连接断开
)

# Session 工厂（expire_on_commit=False 避免 async 场景下访问已过期对象）
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类"""
    pass


async def get_db():
    """
    FastAPI Depends 依赖注入函数。
    每个请求独立 Session，请求结束自动关闭。
    """
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """
    应用启动时调用，自动创建所有表（开发/测试环境）。
    生产环境应使用 Alembic migrate，而非此函数。
    """
    async with engine.begin() as conn:
        # 导入所有模型确保 metadata 注册（顺序重要：base_mixin 最先）
        from app.models import base_mixin  # noqa: F401
        from app.models import user, daily_report, risk_alert, usage_log, audit_log  # noqa: F401
        from app.models import project, project_stage, gate_review, sprint, project_member  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
