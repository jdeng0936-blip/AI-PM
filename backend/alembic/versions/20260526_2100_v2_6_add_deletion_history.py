"""V2.6 Stage 1: 新增 deletion_history 软删除治理表

背景:
  V2.4/V2.5 已把软删覆盖到 daily_reports / projects / sprint_tasks /
  risk_alerts / knowledge_items。V2.6 引入独立 deletion_history 表,让一次
  批量软删对应一条可恢复、可过期、可 dry-run 清理的治理记录。

变更:
  - CREATE TABLE deletion_history
  - 索引:actor_id, table_name, deleted_at, expires_at, restored_at,
    hard_deleted_at, tenant_id

设计说明:
  - project_members.left_at 与 users.is_active 不纳入本表,它们是成员/账号状态。
  - record_ids 用 JSONB array 存 UUID 字符串,保持"一次批量操作一条历史"。
  - actor_id/restored_by ON DELETE SET NULL,避免用户删除影响历史追溯。

Revision ID: 5f0b9d4c2a91
Revises: e8a2c9b6f407
Create Date: 2026-05-26 21:00:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5f0b9d4c2a91"
down_revision: Union[str, None] = "e8a2c9b6f407"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES: tuple[tuple[str, list[str]], ...] = (
    ("ix_deletion_history_actor_id", ["actor_id"]),
    ("ix_deletion_history_table_name", ["table_name"]),
    ("ix_deletion_history_deleted_at", ["deleted_at"]),
    ("ix_deletion_history_expires_at", ["expires_at"]),
    ("ix_deletion_history_restored_at", ["restored_at"]),
    ("ix_deletion_history_hard_deleted_at", ["hard_deleted_at"]),
    ("ix_deletion_history_tenant_id", ["tenant_id"]),
)


def upgrade() -> None:
    """幂等 upgrade — 表/索引存在则跳过。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "deletion_history" not in inspector.get_table_names():
        op.create_table(
            "deletion_history",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("actor_id", sa.Uuid(), nullable=True, comment="执行软删的用户;系统任务可为空"),
            sa.Column("table_name", sa.String(length=64), nullable=False, comment="被软删记录所在业务表名"),
            sa.Column(
                "record_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
                comment="本次批量软删命中的 UUID 列表(JSONB array,字符串形式)",
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False, comment="软删发生时间"),
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=False,
                comment="默认 deleted_at + 30 days;过期后进入硬删清理候选",
            ),
            sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True, comment="该删除批次被恢复的时间"),
            sa.Column("restored_by", sa.Uuid(), nullable=True, comment="执行恢复的用户"),
            sa.Column("hard_deleted_at", sa.DateTime(timezone=True), nullable=True, comment="过期硬删清理完成时间"),
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
            sa.Column("tenant_id", sa.String(length=64), nullable=False, comment="租户隔离标识"),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["restored_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("deletion_history")}
    for ix_name, columns in _INDEXES:
        if ix_name not in existing_indexes:
            op.create_index(op.f(ix_name), "deletion_history", columns, unique=False)


def downgrade() -> None:
    """幂等 downgrade — 索引/表存在则反向移除。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "deletion_history" not in inspector.get_table_names():
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("deletion_history")}
    for ix_name, _columns in reversed(_INDEXES):
        if ix_name in existing_indexes:
            op.drop_index(op.f(ix_name), table_name="deletion_history")
    op.drop_table("deletion_history")
