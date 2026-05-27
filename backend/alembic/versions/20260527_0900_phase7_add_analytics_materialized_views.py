"""Phase 7: 创建历史趋势分析 Materialized Views

背景:
  Phase 7 历史趋势看板需要把日报评分和部门周维度指标预聚合,避免
  Dashboard/API 每次直接扫描 daily_reports。Section 7 规划了
  mv_daily_user_stats 和 mv_weekly_dept_stats 两个 PostgreSQL
  Materialized Views,并由 scheduler 每日凌晨刷新。

变更:
  - CREATE MATERIALIZED VIEW mv_daily_user_stats
  - CREATE MATERIALIZED VIEW mv_weekly_dept_stats
  - 为两个 MV 建唯一索引,满足 REFRESH MATERIALIZED VIEW CONCURRENTLY

实现说明:
  - 代码库真实字段为 users.name / daily_reports.ai_score / created_at,
    分别对应设计稿中的 username / score / submitted_at。
  - 过滤 daily_reports.deleted_at IS NULL,避免历史趋势读到软删数据。
  - 按 tenant_id 纳入唯一键,保持后续多租户扩展一致。

Revision ID: 9b7d3e1c4a20
Revises: 5f0b9d4c2a91
Create Date: 2026-05-27 09:00:00.000000+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b7d3e1c4a20"
down_revision: Union[str, None] = "5f0b9d4c2a91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KNOWLEDGE_DELETED_AT_COMMENT = "软删除时间(V2.5 Stage 3):非 NULL 表示已删除,knowledge / retro / 语义检索默认过滤"
_OLD_KNOWLEDGE_DELETED_AT_COMMENT = "软删除时间(V2.5 Stage 3):非 NULL 表示已删除,所有读取站点默认过滤"


def _relation_exists(bind, relation_name: str) -> bool:
    return bind.execute(sa.text("SELECT to_regclass(:relation_name)"), {"relation_name": relation_name}).scalar() is not None


def _create_index_if_missing(bind, index_name: str, sql: str) -> None:
    if not _relation_exists(bind, index_name):
        op.execute(sa.text(sql))


def _knowledge_deleted_at_exists(bind) -> bool:
    inspector = sa.inspect(bind)
    if "knowledge_items" not in inspector.get_table_names():
        return False
    return "deleted_at" in {col["name"] for col in inspector.get_columns("knowledge_items")}


def _set_knowledge_deleted_at_comment(bind, comment: str) -> None:
    if not _knowledge_deleted_at_exists(bind):
        return
    op.alter_column(
        "knowledge_items",
        "deleted_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
        comment=comment,
    )


def upgrade() -> None:
    """幂等 upgrade — MV/索引已存在则跳过。"""
    bind = op.get_bind()

    # 修正 V2.5 comment 漂移,保持 alembic check 绿色;不改变字段类型或数据。
    _set_knowledge_deleted_at_comment(bind, _KNOWLEDGE_DELETED_AT_COMMENT)

    if not _relation_exists(bind, "mv_daily_user_stats"):
        op.execute(
            sa.text(
                """
                CREATE MATERIALIZED VIEW mv_daily_user_stats AS
                SELECT
                    dr.tenant_id,
                    dr.user_id,
                    u.name AS user_name,
                    u.department,
                    dr.report_date,
                    COUNT(dr.id)::integer AS report_count,
                    ROUND(AVG(dr.ai_score)::numeric, 2) AS avg_score,
                    MAX(dr.ai_score) AS max_score,
                    MIN(dr.ai_score) AS min_score,
                    (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::integer AS pass_count,
                    BOOL_OR(dr.pass_check IS TRUE) AS pass_check,
                    TRUE AS submitted,
                    MAX(dr.created_at) AS last_submitted_at,
                    ROUND(
                        (
                            EXTRACT(
                                EPOCH FROM (
                                    MAX(dr.created_at)
                                    - ((dr.report_date::timestamp + TIME '22:00') AT TIME ZONE 'Asia/Shanghai')
                                )
                            ) / 60.0
                        )::numeric,
                        2
                    ) AS submit_delay_minutes
                FROM daily_reports dr
                JOIN users u ON u.id = dr.user_id
                WHERE u.is_active = TRUE
                  AND dr.deleted_at IS NULL
                GROUP BY dr.tenant_id, dr.user_id, u.name, u.department, dr.report_date
                WITH DATA
                """
            )
        )

    if not _relation_exists(bind, "mv_weekly_dept_stats"):
        op.execute(
            sa.text(
                """
                CREATE MATERIALIZED VIEW mv_weekly_dept_stats AS
                SELECT
                    dr.tenant_id,
                    u.department,
                    DATE_TRUNC('week', dr.report_date::timestamp)::date AS week_start,
                    COUNT(dr.id)::integer AS total_reports,
                    COUNT(DISTINCT dr.user_id)::integer AS active_users,
                    du.total_users,
                    ROUND(AVG(dr.ai_score)::numeric, 2) AS avg_score,
                    (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::integer AS pass_count,
                    ROUND(
                        (
                            (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::numeric
                            / NULLIF(COUNT(dr.id), 0)
                            * 100
                        ),
                        2
                    ) AS pass_rate,
                    ROUND(
                        (
                            COUNT(DISTINCT dr.user_id)::numeric
                            / NULLIF(du.total_users, 0)
                            * 100
                        ),
                        2
                    ) AS submitter_rate
                FROM daily_reports dr
                JOIN users u ON u.id = dr.user_id
                JOIN (
                    SELECT tenant_id, department, COUNT(*)::integer AS total_users
                    FROM users
                    WHERE is_active = TRUE
                    GROUP BY tenant_id, department
                ) du ON du.tenant_id = dr.tenant_id AND du.department = u.department
                WHERE u.is_active = TRUE
                  AND dr.deleted_at IS NULL
                GROUP BY
                    dr.tenant_id,
                    u.department,
                    DATE_TRUNC('week', dr.report_date::timestamp)::date,
                    du.total_users
                WITH DATA
                """
            )
        )

    _create_index_if_missing(
        bind,
        "ix_mv_daily_user_stats_unique",
        """
        CREATE UNIQUE INDEX ix_mv_daily_user_stats_unique
        ON mv_daily_user_stats (tenant_id, user_id, report_date)
        """,
    )
    _create_index_if_missing(
        bind,
        "ix_mv_daily_user_stats_department_report_date",
        """
        CREATE INDEX ix_mv_daily_user_stats_department_report_date
        ON mv_daily_user_stats (tenant_id, department, report_date)
        """,
    )
    _create_index_if_missing(
        bind,
        "ix_mv_weekly_dept_stats_unique",
        """
        CREATE UNIQUE INDEX ix_mv_weekly_dept_stats_unique
        ON mv_weekly_dept_stats (tenant_id, department, week_start)
        """,
    )


def downgrade() -> None:
    """幂等 downgrade — 先删索引,再删 MV。"""
    bind = op.get_bind()

    for index_name in (
        "ix_mv_weekly_dept_stats_unique",
        "ix_mv_daily_user_stats_department_report_date",
        "ix_mv_daily_user_stats_unique",
    ):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))

    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS mv_weekly_dept_stats"))
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS mv_daily_user_stats"))

    _set_knowledge_deleted_at_comment(bind, _OLD_KNOWLEDGE_DELETED_AT_COMMENT)
