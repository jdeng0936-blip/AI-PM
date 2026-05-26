"""V2.4 Stage 2: 给 daily_reports 和 projects 加 deleted_at(软删除标识)

背景:
  V2.4 Stage 2 引入"批量软删"功能。为保护历史数据完整性
  (日报上挂着 ai_score / RiskAlert / Capacity 聚合 / OKR KR 关联),
  采用软删而不是真删。

变更:
  - daily_reports.deleted_at TIMESTAMPTZ NULL + index
  - projects.deleted_at TIMESTAMPTZ NULL + index
  - 两表 list query 默认会加 .where(deleted_at.is_(None)) 过滤已删

设计说明:
  - 用 TIMESTAMPTZ 而非 boolean,保留"什么时候删的"信息便于回溯 / 撤销
  - 加 BTREE 索引支持 `WHERE deleted_at IS NULL` 的高效过滤
  - 不连带 cascade(删项目不连带删日报),保留历史日报的项目关联
  - downgrade 反向删除

幂等保护:
  - inspector.get_columns / get_indexes 检测存在则跳过

Revision ID: c3e5f0a7b218
Revises: b2c4d8e9f102
Create Date: 2026-05-26 10:00:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e5f0a7b218"
down_revision: Union[str, None] = "b2c4d8e9f102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """幂等 upgrade — 列/索引已存在则跳过。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── daily_reports.deleted_at ──────────────────────────────────
    existing_cols = {c["name"] for c in inspector.get_columns("daily_reports")}
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("daily_reports")}

    if "deleted_at" not in existing_cols:
        op.add_column(
            "daily_reports",
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="软删除时间(V2.4):非 NULL 表示已删除,list 默认过滤",
            ),
        )
    if "ix_daily_reports_deleted_at" not in existing_indexes:
        op.create_index(
            op.f("ix_daily_reports_deleted_at"),
            "daily_reports",
            ["deleted_at"],
            unique=False,
        )

    # ── projects.deleted_at ───────────────────────────────────────
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("projects")}
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("projects")}

    if "deleted_at" not in existing_cols:
        op.add_column(
            "projects",
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="软删除时间(V2.4):非 NULL 表示已删除,list 默认过滤",
            ),
        )
    if "ix_projects_deleted_at" not in existing_indexes:
        op.create_index(
            op.f("ix_projects_deleted_at"),
            "projects",
            ["deleted_at"],
            unique=False,
        )


def downgrade() -> None:
    """幂等 downgrade — 索引/列存在则反向移除。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # projects 先(后建的先删)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("projects")}
    existing_cols = {c["name"] for c in inspector.get_columns("projects")}
    if "ix_projects_deleted_at" in existing_indexes:
        op.drop_index(op.f("ix_projects_deleted_at"), table_name="projects")
    if "deleted_at" in existing_cols:
        op.drop_column("projects", "deleted_at")

    inspector = sa.inspect(bind)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("daily_reports")}
    existing_cols = {c["name"] for c in inspector.get_columns("daily_reports")}
    if "ix_daily_reports_deleted_at" in existing_indexes:
        op.drop_index(op.f("ix_daily_reports_deleted_at"), table_name="daily_reports")
    if "deleted_at" in existing_cols:
        op.drop_column("daily_reports", "deleted_at")
