"""V2.0 baseline: 全表 + Week 1-8 schema 一次性建齐

Revision ID: v2_0_baseline
Revises: 7c681b8e950c
Create Date: 2026-05-19 18:00:00+08:00

设计:
- 老 initial_schema 是空的(dev 模式靠 create_all 隐式建),所以本迁移
  作为「V2.0 出厂版」,把所有 20 张表 + Week 1-8 字段补丁一次性纳管。
- 用 SQLAlchemy metadata.create_all(checkfirst=True) 兜底:
  · 全新环境:一口气建齐
  · dev 跑过的环境:已存在的表跳过,只补缺的
  · 中途升级:不会重复建已有表
- 字段补丁(alter column / add column)用 inspector 检测,只加缺的列。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# ── revision identifiers ──
revision: str = "v2_0_baseline"
down_revision: Union[str, None] = "7c681b8e950c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1) 用 SQLAlchemy metadata.create_all 一次性兜底建 V2.0 所有 20 张表
       (已存在的表自动跳过)
    2) 对 Week 1-8 新增的字段单独做 ALTER ADD COLUMN(检测列存在再加)
    """
    # ── Step 1: 建表(checkfirst 模式) ──
    # 触发所有 model import,把 metadata 填满
    import app.models  # noqa: F401
    from app.database import Base

    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind, checkfirst=True)

    # ── Step 2: 已有表的字段补丁 ──
    inspector = sa.inspect(bind)

    def add_column_if_missing(
        table: str, column_name: str, column_def: sa.Column,
    ) -> None:
        if table not in inspector.get_table_names():
            return  # 表本身不存在(应该已被 create_all 建了,但兜底跳过)
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column_name in existing:
            return
        op.add_column(table, column_def)

    # Week 1:User 加钉钉 ID
    add_column_if_missing(
        "users",
        "dingtalk_userid",
        sa.Column("dingtalk_userid", sa.String(64), nullable=True, unique=True),
    )

    # Week 5:KeyResult 加 unit + description
    add_column_if_missing(
        "key_results",
        "unit",
        sa.Column("unit", sa.String(20), nullable=True),
    )
    add_column_if_missing(
        "key_results",
        "description",
        sa.Column("description", sa.Text, nullable=True),
    )

    # Week 7:DailyReport 加 mentioned_task_ids
    add_column_if_missing(
        "daily_reports",
        "mentioned_task_ids",
        sa.Column(
            "mentioned_task_ids",
            sa.ARRAY(sa.String),
            nullable=True,
            server_default="{}",
        ),
    )

    # ── Step 3: 关键索引补丁(checkfirst) ──
    _ensure_index(inspector, "ix_notifications_user_id", "notifications", ["user_id"])
    _ensure_index(inspector, "ix_attachments_uploaded_by", "attachments", ["uploaded_by"])
    _ensure_index(inspector, "ix_kr_progress_logs_kr_id", "kr_progress_logs", ["kr_id"])
    _ensure_index(inspector, "ix_sprint_tasks_sprint_id", "sprint_tasks", ["sprint_id"])
    _ensure_index(inspector, "ix_burndown_snapshots_sprint_id", "burndown_snapshots", ["sprint_id"])
    _ensure_index(inspector, "ix_capacity_snapshots_user_id", "capacity_snapshots", ["user_id"])
    _ensure_index(inspector, "ix_capacity_snapshots_sprint_id", "capacity_snapshots", ["sprint_id"])


def _ensure_index(inspector, name: str, table: str, columns: list[str]) -> None:
    """只在缺索引时建立(checkfirst 等价物)"""
    if table not in inspector.get_table_names():
        return
    existing = {ix["name"] for ix in inspector.get_indexes(table)}
    if name in existing:
        return
    op.create_index(name, table, columns)


def downgrade() -> None:
    """
    保守降级:只回滚 Week 1-8 新增的列和表,不动 V1.0 原有 schema。
    数据完全清除,生产环境慎用。
    """
    # 删 Week 1-8 新表(顺序:外键依赖最末的先删)
    drop_tables = [
        "capacity_snapshots",
        "burndown_snapshots",
        "sprint_tasks",
        "kr_progress_logs",
        "attachments",
        "notifications",
    ]
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for t in drop_tables:
        if t in existing:
            op.drop_table(t)

    # 删 Week 1-8 加的列(再 inspect 一次,因为表已变)
    inspector = sa.inspect(bind)

    def drop_column_if_exists(table: str, col: str) -> None:
        if table not in inspector.get_table_names():
            return
        if col not in {c["name"] for c in inspector.get_columns(table)}:
            return
        op.drop_column(table, col)

    drop_column_if_exists("daily_reports", "mentioned_task_ids")
    drop_column_if_exists("key_results", "description")
    drop_column_if_exists("key_results", "unit")
    drop_column_if_exists("users", "dingtalk_userid")
