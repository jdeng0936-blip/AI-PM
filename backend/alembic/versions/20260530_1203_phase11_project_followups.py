"""Phase 11 T-1106: project follow-ups and temporary resolution summary.

Revision ID: e6f7a8b9c0d1
Revises: d4f7a8b9c1e2
Create Date: 2026-05-30 12:03:00

T-1106 临时工单跟进追踪闭环:
  - 新建 project_follow_ups append-only 跟进记录表
  - 新增 projects.resolution_summary 处理结果字段
  - 临时工单 stale 健康度按最近跟进时间联动
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision = "e6f7a8b9c0d1"
down_revision = "d4f7a8b9c1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_exists = "project_follow_ups" in inspector.get_table_names()

    if not table_exists:
        op.create_table(
            "project_follow_ups",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(
                ["project_id"],
                ["projects.id"],
                name="fk_project_follow_ups_project_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["created_by"],
                ["users.id"],
                name="fk_project_follow_ups_created_by",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = set()
    if table_exists:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("project_follow_ups")}
    if "ix_project_follow_ups_project_id" not in existing_indexes:
        op.create_index(
            "ix_project_follow_ups_project_id",
            "project_follow_ups",
            ["project_id"],
        )
    if "ix_project_follow_ups_project_created" not in existing_indexes:
        op.create_index(
            "ix_project_follow_ups_project_created",
            "project_follow_ups",
            ["project_id", "created_at"],
        )

    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "resolution_summary" not in project_columns:
        op.add_column(
            "projects",
            sa.Column(
                "resolution_summary",
                sa.String(length=2048),
                nullable=True,
                comment="临时工单处理结果(T-1106):仅 is_temporary=True 完工时强制填写;主干项目永久 NULL",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "resolution_summary" in project_columns:
        op.drop_column("projects", "resolution_summary")

    if "project_follow_ups" in inspector.get_table_names():
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("project_follow_ups")}
        if "ix_project_follow_ups_project_created" in existing_indexes:
            op.drop_index("ix_project_follow_ups_project_created", table_name="project_follow_ups")
        if "ix_project_follow_ups_project_id" in existing_indexes:
            op.drop_index("ix_project_follow_ups_project_id", table_name="project_follow_ups")
        op.drop_table("project_follow_ups")
