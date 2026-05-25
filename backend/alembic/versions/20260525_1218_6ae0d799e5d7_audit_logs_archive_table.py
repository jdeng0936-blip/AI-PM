"""V2.1: 新增 audit_logs_archive 归档表

背景:
  audit_logs 主表单调追加,长期会无限膨胀。Stage 1 引入月度归档策略,
  scheduled_tasks.archive_old_audit_logs 每月 1 日 02:00 把 12 个月以上的
  审计记录从主表迁移到 audit_logs_archive,保留主表查询性能。

变更:
  - CREATE TABLE audit_logs_archive(结构与 audit_logs 一致 + archived_at)
  - 索引:ix_audit_logs_archive_user_id, ix_audit_logs_archive_tenant_id
  - FK:user_id → users.id, created_by → users.id ON DELETE SET NULL

幂等保护(遵循 docs/MIGRATION_GUIDE.md):
  - inspector.get_table_names() 检测 audit_logs_archive 已存在(被 v2_0_baseline
    create_all 兜底建过的场景)则跳过 create_table
  - 索引同样检测后建

Revision ID: 6ae0d799e5d7
Revises: d2c623c6291a
Create Date: 2026-05-25 12:18:01.466082+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6ae0d799e5d7"
down_revision: Union[str, None] = "d2c623c6291a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """幂等 upgrade — 表/索引存在则跳过。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "audit_logs_archive" not in inspector.get_table_names():
        op.create_table(
            "audit_logs_archive",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column(
                "action",
                sa.String(length=50),
                nullable=False,
                comment="login | submit_report | change_password | admin_action",
            ),
            sa.Column("ip_address", sa.String(length=45), nullable=True, comment="客户端 IP"),
            sa.Column(
                "detail",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment="附加信息 JSON",
            ),
            sa.Column(
                "archived_at",
                postgresql.TIMESTAMP(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
                comment="归档时间(scheduled_tasks 迁移本条记录时填入)",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
                comment="记录创建时间",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
                comment="记录最后更新时间",
            ),
            sa.Column("created_by", sa.Uuid(), nullable=True, comment="创建者 user.id"),
            sa.Column(
                "tenant_id", sa.String(length=64), nullable=False, comment="租户隔离标识"
            ),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("audit_logs_archive")}
    if "ix_audit_logs_archive_tenant_id" not in existing_indexes:
        op.create_index(
            op.f("ix_audit_logs_archive_tenant_id"),
            "audit_logs_archive",
            ["tenant_id"],
            unique=False,
        )
    if "ix_audit_logs_archive_user_id" not in existing_indexes:
        op.create_index(
            op.f("ix_audit_logs_archive_user_id"),
            "audit_logs_archive",
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    """幂等 downgrade — 索引/表存在则 drop。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "audit_logs_archive" in inspector.get_table_names():
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("audit_logs_archive")}
        if "ix_audit_logs_archive_user_id" in existing_indexes:
            op.drop_index(
                op.f("ix_audit_logs_archive_user_id"), table_name="audit_logs_archive"
            )
        if "ix_audit_logs_archive_tenant_id" in existing_indexes:
            op.drop_index(
                op.f("ix_audit_logs_archive_tenant_id"), table_name="audit_logs_archive"
            )
        op.drop_table("audit_logs_archive")
