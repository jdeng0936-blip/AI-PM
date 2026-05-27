"""Phase 9: 修正 KPI 目标唯一约束的 NULL 语义

背景:
  T-901 验收发现 PostgreSQL 默认 UNIQUE 约束采用 NULL DISTINCT 语义,
  允许重复插入 (global, NULL, submit_rate, monthly),会导致全局 KPI 目标重复。

变更:
  - 删除旧的 uq_kpi_targets_scope_metric_period 唯一约束。
  - 使用 PostgreSQL 15+ 的 NULLS NOT DISTINCT 语义重建同名唯一约束。

实现说明:
  - 通过 Alembic create_unique_constraint 的 postgresql_nulls_not_distinct=True
    方言参数表达约束语义,避免手写 ALTER CONSTRAINT SQL。
  - downgrade 恢复为 PostgreSQL 默认 NULLS DISTINCT 语义,保持补丁可回滚。

Revision ID: b4f6a8d2c9e1
Revises: c7a9f1e2d4b6
Create Date: 2026-05-27 13:17:00.000000+08:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4f6a8d2c9e1"
down_revision: Union[str, None] = "c7a9f1e2d4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_kpi_targets_scope_metric_period", "kpi_targets", type_="unique")
    op.create_unique_constraint(
        "uq_kpi_targets_scope_metric_period",
        "kpi_targets",
        ["scope", "scope_value", "metric", "period"],
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_constraint("uq_kpi_targets_scope_metric_period", "kpi_targets", type_="unique")
    op.create_unique_constraint(
        "uq_kpi_targets_scope_metric_period",
        "kpi_targets",
        ["scope", "scope_value", "metric", "period"],
    )
