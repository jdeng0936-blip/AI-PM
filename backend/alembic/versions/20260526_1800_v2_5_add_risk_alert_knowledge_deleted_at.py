"""V2.5 Stage 3: 给 risk_alerts + knowledge_items 加 deleted_at(软删除)

背景:
  V2.5 Stage 3 把软删范式扩展到 RiskAlert 与 KnowledgeItem。
  - RiskAlert: 直接物理删会破坏 ERP 解卡历史 / 周报 / retro / chat AI 引用;改成软删。
  - KnowledgeItem: 知识库 / retro / 语义搜索均依赖 view_count/helpful_count 历史聚合;
    硬删会丢失 source_id 锚点(如复盘对应的 sprint_id)与统计数据,改成软删。

变更:
  - risk_alerts.deleted_at TIMESTAMPTZ NULL + BTREE 索引
  - knowledge_items.deleted_at TIMESTAMPTZ NULL + BTREE 索引

设计说明:
  - 用 TIMESTAMPTZ 与 V2.4/V2.5 Stage 2 保持一致,供回收站排序与撤销 toast
  - 索引支持 `WHERE deleted_at IS NULL` 的高效过滤(列表是核心读取路径)
  - HNSW 索引不受影响(pgvector 向量索引不依赖 deleted_at)
  - downgrade 反向删除

幂等保护:
  - inspector.get_columns / get_indexes 检测存在则跳过

Revision ID: e8a2c9b6f407
Revises: d4f6a1b8c329
Create Date: 2026-05-26 18:00:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8a2c9b6f407"
down_revision: Union[str, None] = "d4f6a1b8c329"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_deleted_at(table: str, ix_name: str, inspector) -> None:
    existing_cols = {c["name"] for c in inspector.get_columns(table)}
    existing_indexes = {ix["name"] for ix in inspector.get_indexes(table)}
    if "deleted_at" not in existing_cols:
        op.add_column(
            table,
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="软删除时间(V2.5 Stage 3):非 NULL 表示已删除,所有读取站点默认过滤",
            ),
        )
    if ix_name not in existing_indexes:
        op.create_index(op.f(ix_name), table, ["deleted_at"], unique=False)


def _drop_deleted_at(table: str, ix_name: str, inspector) -> None:
    existing_indexes = {ix["name"] for ix in inspector.get_indexes(table)}
    existing_cols = {c["name"] for c in inspector.get_columns(table)}
    if ix_name in existing_indexes:
        op.drop_index(op.f(ix_name), table_name=table)
    if "deleted_at" in existing_cols:
        op.drop_column(table, "deleted_at")


def upgrade() -> None:
    """幂等 upgrade — 列/索引已存在则跳过。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _add_deleted_at("risk_alerts", "ix_risk_alerts_deleted_at", inspector)
    _add_deleted_at("knowledge_items", "ix_knowledge_items_deleted_at", inspector)


def downgrade() -> None:
    """幂等 downgrade — 索引/列存在则反向移除。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _drop_deleted_at("knowledge_items", "ix_knowledge_items_deleted_at", inspector)
    _drop_deleted_at("risk_alerts", "ix_risk_alerts_deleted_at", inspector)
