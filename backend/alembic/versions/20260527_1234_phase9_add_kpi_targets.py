"""Phase 9: 创建 KPI 目标设定表

背景:
  Phase 9 KPI 目标设定需要持久化全局 / 部门 / 岗位三种 scope 下的
  submit_rate / avg_score / sprint_completion / blocker_resolve_days 四类目标,
  为后续 service 与 dashboard 达成率计算提供数据层基座。

变更:
  - 新建 PostgreSQL ENUM 类型 kpi_scope / kpi_metric / kpi_period。
  - 新建 kpi_targets 表,包含目标字段、BaseMixin 通用字段、唯一约束与查询索引。
  - 种入 4 条全局 / 技术部 baseline KPI 目标。

实现说明:
  - id 保留 implementation-plan §9 的 SERIAL 语义,落地为 Integer autoincrement。
  - created_by 按项目真实 users.id 类型校正为 UUID FK,并继承 BaseMixin 的字段约定。
  - downgrade 显式删除表、索引与 ENUM 类型,确保双向迁移可重复运行。

Revision ID: c7a9f1e2d4b6
Revises: 9b7d3e1c4a20
Create Date: 2026-05-27 12:34:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7a9f1e2d4b6"
down_revision: Union[str, None] = "9b7d3e1c4a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    kpi_scope = postgresql.ENUM("global", "department", "job_title", name="kpi_scope", create_type=False)
    kpi_metric = postgresql.ENUM(
        "submit_rate",
        "avg_score",
        "sprint_completion",
        "blocker_resolve_days",
        name="kpi_metric",
        create_type=False,
    )
    kpi_period = postgresql.ENUM("weekly", "monthly", "quarterly", name="kpi_period", create_type=False)
    kpi_scope.create(bind, checkfirst=True)
    kpi_metric.create(bind, checkfirst=True)
    kpi_period.create(bind, checkfirst=True)

    if not inspector.has_table("kpi_targets"):
        op.create_table(
            "kpi_targets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scope", kpi_scope, nullable=False),
            sa.Column("scope_value", sa.String(50), nullable=True),
            sa.Column("metric", kpi_metric, nullable=False),
            sa.Column("target_value", sa.Float(), nullable=False),
            sa.Column("period", kpi_period, nullable=False, server_default="monthly"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
                comment="记录创建时间",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
                comment="记录最后更新时间",
            ),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True, comment="创建者 user.id"),
            sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default", comment="租户隔离标识"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint(
                "scope",
                "scope_value",
                "metric",
                "period",
                name="uq_kpi_targets_scope_metric_period",
            ),
        )

    op.execute("CREATE INDEX IF NOT EXISTS ix_kpi_targets_scope_metric ON kpi_targets (scope, metric)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kpi_targets_tenant_id ON kpi_targets (tenant_id)")

    metric_rows = bind.execute(
        sa.text(
            """
            SELECT enumlabel
            FROM pg_enum
            JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
            WHERE pg_type.typname = 'kpi_metric'
            """
        )
    ).scalars()
    metric_labels = set(metric_rows)
    completion_metric = "objective_completion" if "objective_completion" in metric_labels else "sprint_completion"

    seed_rows = [
        ("global", None, "submit_rate", 95.0),
        ("global", None, "avg_score", 75.0),
        ("global", None, "blocker_resolve_days", 3.0),
        ("department", "技术部", completion_metric, 80.0),
    ]
    for scope, scope_value, metric, target_value in seed_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO kpi_targets (scope, scope_value, metric, target_value, period, tenant_id)
                SELECT
                    CAST(:scope AS kpi_scope),
                    CAST(:scope_value AS varchar),
                    CAST(:metric AS kpi_metric),
                    :target_value,
                    'monthly'::kpi_period,
                    'default'
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM kpi_targets
                    WHERE scope = CAST(:scope AS kpi_scope)
                      AND scope_value IS NOT DISTINCT FROM CAST(:scope_value AS varchar)
                      AND metric = CAST(:metric AS kpi_metric)
                      AND period = 'monthly'
                      AND tenant_id = 'default'
                )
                """
            ),
            {
                "scope": scope,
                "scope_value": scope_value,
                "metric": metric,
                "target_value": target_value,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_kpi_targets_tenant_id", table_name="kpi_targets")
    op.drop_index("ix_kpi_targets_scope_metric", table_name="kpi_targets")
    op.drop_table("kpi_targets")
    postgresql.ENUM(name="kpi_period").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="kpi_metric").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="kpi_scope").drop(op.get_bind(), checkfirst=True)
