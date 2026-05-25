"""V2.3: 给 projects 加 is_temporary 标识(临时工单项目)

背景:
  当前项目模型是重型 IPD 项目(5 阶段 + Sprint + 任务)。日常临时工单(bug 修复、
  改价、ERP 维护这类零散活儿)没有合适的项目去挂,员工只能 project_id=NULL。
  结果 Dashboard 看不出"主干工时 vs 临时支撑工时"占比,资源水位也算不上。

变更:
  - projects 表加 is_temporary BOOL NOT NULL DEFAULT false
  - 加 ix_projects_is_temporary BTREE 索引(支持按 is_temporary 快速过滤,
    submit-report 项目下拉按 is_temporary desc 置顶时也用到)

设计说明:
  - 双重默认值:model 层 default=False + server_default='false'
    既有数据行可被 alembic 安全填充,新 INSERT 不写该字段也不会失败
  - 不加 partial index — is_temporary=true 的项目通常很少(管理层手工建),
    总表数据量小,普通 BTREE 已经足够;且 partial index 在 SQLite 测试环境
    兼容性略差
  - 关联 Sprint/任务等其他表无需改动,临时项目走 sprint_number=0 的虚拟
    "Backlog" Sprint(在 routers/projects.py 的 create 逻辑里建,不在本
    migration 处理)

幂等保护(遵循 docs/MIGRATION_GUIDE.md):
  - inspector.get_columns 检测列已存在则跳过 add_column
  - inspector.get_indexes 检测索引已存在则跳过 create_index

Revision ID: a1f3b7c2d801
Revises: 94aa8bc45089
Create Date: 2026-05-25 15:00:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f3b7c2d801"
down_revision: Union[str, None] = "94aa8bc45089"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """幂等 upgrade — 列/索引已存在则跳过。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_cols = {c["name"] for c in inspector.get_columns("projects")}
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("projects")}

    if "is_temporary" not in existing_cols:
        op.add_column(
            "projects",
            sa.Column(
                "is_temporary",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
                comment="是否为临时工单项目(V2.3):跳过 5 阶段初始化,不进红黄绿矩阵",
            ),
        )

    if "ix_projects_is_temporary" not in existing_indexes:
        op.create_index(
            op.f("ix_projects_is_temporary"),
            "projects",
            ["is_temporary"],
            unique=False,
        )


def downgrade() -> None:
    """幂等 downgrade — 索引/列存在则反向移除。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("projects")}
    existing_cols = {c["name"] for c in inspector.get_columns("projects")}

    if "ix_projects_is_temporary" in existing_indexes:
        op.drop_index(op.f("ix_projects_is_temporary"), table_name="projects")
    if "is_temporary" in existing_cols:
        op.drop_column("projects", "is_temporary")
