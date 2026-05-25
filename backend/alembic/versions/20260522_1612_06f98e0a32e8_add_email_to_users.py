"""V2.1: 为 users 表新增 email 字段 + 唯一索引

背景:
  邮件通知通道(services/email_api.py)上线后,需要按员工 email 推送 V2.0 的
  催报、风险预警、战情简报等。原 users 表只有微信/钉钉账号,缺 email 字段。

变更:
  - ADD COLUMN users.email VARCHAR(128) NULL  COMMENT '员工邮箱,用于邮件通知'
  - CREATE UNIQUE INDEX ix_users_email ON users(email)

兼容性:
  - email 允许 NULL,历史用户无需回填即可继续使用
  - 唯一索引下 NULL 互不冲突(Postgres 行为)

Revision ID: 06f98e0a32e8
Revises: v2_1_notification_read_at
Create Date: 2026-05-22 16:12:02.166753+08:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '06f98e0a32e8'
down_revision: Union[str, None] = 'v2_1_notification_read_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """幂等 upgrade — 兼容 v2_0_baseline 用最新 ORM create_all 兜底建表的场景。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "users" not in inspector.get_table_names():
        return  # users 表不存在,baseline 应该已经建过,理论上不会到这

    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    if "email" not in existing_cols:
        op.add_column(
            "users",
            sa.Column("email", sa.String(length=128), nullable=True, comment="员工邮箱，用于邮件通知"),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("users")}
    if "ix_users_email" not in existing_indexes:
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("users")}
    if "ix_users_email" in existing_indexes:
        op.drop_index(op.f("ix_users_email"), table_name="users")

    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    if "email" in existing_cols:
        op.drop_column("users", "email")
