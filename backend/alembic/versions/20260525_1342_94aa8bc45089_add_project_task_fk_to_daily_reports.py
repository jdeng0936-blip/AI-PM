"""V2.2: 给 daily_reports 加 project_id + sprint_task_id 外键

背景:
  当前晨规划/日报表单只有 raw_input_text + parsed_content,员工提交的工作
  无法结构化挂钩到具体项目和 Sprint 任务。Dashboard 按项目聚合日报需要
  从 sprint_task → sprint → project 多级 join,且当员工没挂 task 时就完全
  失联。

变更:
  - daily_reports 加 project_id UUID FK → projects.id ON DELETE SET NULL
  - daily_reports 加 sprint_task_id UUID FK → sprint_tasks.id ON DELETE SET NULL
  - 两列都 nullable(老数据兼容,且员工可选不挂)
  - 两列各加 BTREE index 以加速按项目/按任务聚合查询

设计说明:
  - sprint_task 已有 kr_id FK → key_results,所以挂 task 即间接挂 OKR KR
    本 migration 不在 daily_reports 加 kr_id(避免冗余 + 歧义)
  - 已有 mentioned_task_ids ARRAY[String] 保留作为"次要多任务关联"(向后兼容)
  - project_id 与 sprint_task→project 是冗余的;接受冗余换查询性能

幂等保护(遵循 docs/MIGRATION_GUIDE.md):
  - inspector.get_columns 检测列已存在则跳过 add_column
  - inspector.get_indexes 检测索引已存在则跳过 create_index
  - inspector.get_foreign_keys 检测 FK 已存在则跳过(避免 add_column 自带 FK
    + 之前手工建过同名 FK 时的 DuplicateObject)

Revision ID: 94aa8bc45089
Revises: 6ae0d799e5d7
Create Date: 2026-05-25 13:42:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "94aa8bc45089"
down_revision: Union[str, None] = "6ae0d799e5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """幂等 upgrade — 列/索引/FK 已存在则跳过。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_cols = {c["name"] for c in inspector.get_columns("daily_reports")}
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("daily_reports") if fk.get("name")}
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("daily_reports")}

    # ── project_id ───────────────────────────────────────────────
    if "project_id" not in existing_cols:
        op.add_column(
            "daily_reports",
            sa.Column(
                "project_id",
                sa.Uuid(),
                nullable=True,
                comment="日报关联的项目(可选)",
            ),
        )
    if "fk_daily_reports_project_id_projects" not in existing_fks:
        op.create_foreign_key(
            "fk_daily_reports_project_id_projects",
            "daily_reports",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "ix_daily_reports_project_id" not in existing_indexes:
        op.create_index(
            op.f("ix_daily_reports_project_id"),
            "daily_reports",
            ["project_id"],
            unique=False,
        )

    # ── sprint_task_id ───────────────────────────────────────────
    # 刷新 inspector(add_column 后列才"已存在")
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("daily_reports")}
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("daily_reports") if fk.get("name")}
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("daily_reports")}

    if "sprint_task_id" not in existing_cols:
        op.add_column(
            "daily_reports",
            sa.Column(
                "sprint_task_id",
                sa.Uuid(),
                nullable=True,
                comment="日报关联的主任务(可选,通过 task→kr 间接挂 OKR)",
            ),
        )
    if "fk_daily_reports_sprint_task_id_sprint_tasks" not in existing_fks:
        op.create_foreign_key(
            "fk_daily_reports_sprint_task_id_sprint_tasks",
            "daily_reports",
            "sprint_tasks",
            ["sprint_task_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "ix_daily_reports_sprint_task_id" not in existing_indexes:
        op.create_index(
            op.f("ix_daily_reports_sprint_task_id"),
            "daily_reports",
            ["sprint_task_id"],
            unique=False,
        )


def downgrade() -> None:
    """幂等 downgrade — 索引/FK/列存在则反向移除。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("daily_reports")}
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("daily_reports") if fk.get("name")}
    existing_cols = {c["name"] for c in inspector.get_columns("daily_reports")}

    if "ix_daily_reports_sprint_task_id" in existing_indexes:
        op.drop_index(op.f("ix_daily_reports_sprint_task_id"), table_name="daily_reports")
    if "fk_daily_reports_sprint_task_id_sprint_tasks" in existing_fks:
        op.drop_constraint(
            "fk_daily_reports_sprint_task_id_sprint_tasks", "daily_reports", type_="foreignkey"
        )
    if "sprint_task_id" in existing_cols:
        op.drop_column("daily_reports", "sprint_task_id")

    if "ix_daily_reports_project_id" in existing_indexes:
        op.drop_index(op.f("ix_daily_reports_project_id"), table_name="daily_reports")
    if "fk_daily_reports_project_id_projects" in existing_fks:
        op.drop_constraint(
            "fk_daily_reports_project_id_projects", "daily_reports", type_="foreignkey"
        )
    if "project_id" in existing_cols:
        op.drop_column("daily_reports", "project_id")
