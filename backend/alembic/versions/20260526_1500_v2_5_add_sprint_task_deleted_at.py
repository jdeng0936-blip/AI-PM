"""V2.5 Stage 2: 给 sprint_tasks 加 deleted_at(软删除标识)

背景:
  V2.5 Stage 2 把 V2.4 的批量软删范式扩展到 Sprint 任务。
  任务直接物理删会破坏燃尽快照历史、capacity 聚合、daily_report.sprint_task_id 关联;
  采用软删保护审计链与可恢复性。

变更:
  - sprint_tasks.deleted_at TIMESTAMPTZ NULL + BTREE 索引
  - 列表 / 燃尽计算 / 关键路径 / capacity / chat_tools 全部默认 .where(deleted_at.is_(None))
  - 单条 DELETE 改成软删;新增 batch / batch-restore / deleted 三个端点

设计说明:
  - 用 TIMESTAMPTZ 而非 boolean,保留时间戳供撤销 toast 与回收站排序
  - 索引支持 `WHERE deleted_at IS NULL` 的高效过滤(任务列表是核心查询路径)
  - BurndownSnapshot 历史不受影响(snapshot 是按日聚合的派生数据,不依赖 task.deleted_at)
  - downgrade 反向删除

幂等保护:
  - inspector.get_columns / get_indexes 检测存在则跳过

Revision ID: d4f6a1b8c329
Revises: c3e5f0a7b218
Create Date: 2026-05-26 15:00:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f6a1b8c329"
down_revision: Union[str, None] = "c3e5f0a7b218"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """幂等 upgrade — 列/索引已存在则跳过。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_cols = {c["name"] for c in inspector.get_columns("sprint_tasks")}
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("sprint_tasks")}

    if "deleted_at" not in existing_cols:
        op.add_column(
            "sprint_tasks",
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="软删除时间(V2.5):非 NULL 表示已删除,list/燃尽/关键路径默认过滤",
            ),
        )
    if "ix_sprint_tasks_deleted_at" not in existing_indexes:
        op.create_index(
            op.f("ix_sprint_tasks_deleted_at"),
            "sprint_tasks",
            ["deleted_at"],
            unique=False,
        )


def downgrade() -> None:
    """幂等 downgrade — 索引/列存在则反向移除。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("sprint_tasks")}
    existing_cols = {c["name"] for c in inspector.get_columns("sprint_tasks")}
    if "ix_sprint_tasks_deleted_at" in existing_indexes:
        op.drop_index(op.f("ix_sprint_tasks_deleted_at"), table_name="sprint_tasks")
    if "deleted_at" in existing_cols:
        op.drop_column("sprint_tasks", "deleted_at")
