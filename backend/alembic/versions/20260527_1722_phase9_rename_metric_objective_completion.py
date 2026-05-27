"""Phase 9: 统一 KPI metric 枚举命名为 objective_completion

背景:
  T-907 验收发现前后端 KPI metric 命名漂移:后端使用 sprint_completion,
  前端 T-905/T-906 已按 OKR 语义使用 objective_completion,导致前端提交
  OKR 完成率时被后端枚举校验拒绝。

变更:
  - 将 PostgreSQL native ENUM kpi_metric 中的 sprint_completion 原子重命名为
    objective_completion。
  - 利用 ALTER TYPE RENAME VALUE 自动同步既有 kpi_targets 数据,不手写 UPDATE。

实现说明:
  - PostgreSQL 16 支持事务内 ALTER TYPE ... RENAME VALUE。
  - downgrade 反向重命名,保持 Phase 9 修补迁移可回滚。

Revision ID: e8c4a1d9f2b0
Revises: b4f6a8d2c9e1
Create Date: 2026-05-27 17:22:00.000000+08:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8c4a1d9f2b0"
down_revision: Union[str, None] = "b4f6a8d2c9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE kpi_metric RENAME VALUE 'sprint_completion' TO 'objective_completion'")


def downgrade() -> None:
    op.execute("ALTER TYPE kpi_metric RENAME VALUE 'objective_completion' TO 'sprint_completion'")
