"""Phase 10 / T-1002: project_members 加 partial unique index

实际背景:
  T-1001 勘察发现 ProjectMember 模型层未声明联合 UNIQUE,允许同一员工在同一项目内
  重复挂多次,污染 health_engine 按成员聚合的统计结果。plan §10 原文已写明
  UNIQUE(project_id, user_id),但 V2.0 实际落地遗漏。

变更:
  - 新建 partial unique index ix_project_members_project_user_active on
    project_members(project_id, user_id) WHERE left_at IS NULL。
  - 同步 ORM ProjectMember.__table_args__,保持模型声明与数据库 schema 一致。

实现说明:
  - 使用 partial unique index 而非简单 UNIQUE,保留“员工离场后再加入”的工作流:
    员工 left_at NOT NULL 后即为历史行,不再受当前在场唯一性约束。
  - 该 index 同时覆盖按项目和员工查找当前在场成员的访问路径,无需额外独立 index。
  - upgrade 前若现有数据存在重复 (project_id, user_id) WHERE left_at IS NULL,
    upgrade 会因 UNIQUE 冲突失败;本 migration 不做自动数据清洗。

Revision ID: 4f8e370435ea
Revises: e8c4a1d9f2b0
Create Date: 2026-05-27 18:50:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f8e370435ea"
down_revision: Union[str, None] = "e8c4a1d9f2b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_project_members_project_user_active",
        "project_members",
        ["project_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_members_project_user_active",
        table_name="project_members",
    )
