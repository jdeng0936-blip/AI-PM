"""
alembic/env.py — Alembic 异步迁移环境配置
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 引入应用配置和所有模型
from app.config import settings
from app.database import Base
from app.models import (  # noqa: F401
    user, daily_report, risk_alert, usage_log, audit_log,
    project, project_stage, gate_review, sprint, project_member,
    base_mixin,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 从 settings 中覆盖数据库 URL（支持多环境）
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """离线模式迁移（生成 SQL 文件而不直接执行）"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步模式迁移（适配 asyncpg）"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
