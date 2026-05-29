"""Phase 13 T-1301: daily report morning-evening close loop + supervised tracking.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-30 13:19:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def _enum_names(bind: sa.engine.Connection) -> set[str]:
    return {
        row[0]
        for row in bind.execute(
            sa.text("SELECT typname FROM pg_type WHERE typtype='e'")
        ).fetchall()
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_enums = _enum_names(bind)
    report_type_enum = postgresql.ENUM(
        "morning_plan",
        "evening_review",
        "ad_hoc",
        name="daily_report_type",
        create_type=False,
    )
    if "daily_report_type" not in existing_enums:
        report_type_enum.create(bind, checkfirst=False)

    planned_status_enum = postgresql.ENUM(
        "done",
        "partial",
        "delayed",
        "cancelled",
        name="daily_report_planned_status",
        create_type=False,
    )
    if "daily_report_planned_status" not in existing_enums:
        planned_status_enum.create(bind, checkfirst=False)

    supervised_status_enum = postgresql.ENUM(
        "open",
        "closed",
        name="supervised_status",
        create_type=False,
    )
    if "supervised_status" not in existing_enums:
        supervised_status_enum.create(bind, checkfirst=False)

    daily_reports_columns = {column["name"] for column in inspector.get_columns("daily_reports")}
    daily_reports_indexes = {idx["name"] for idx in inspector.get_indexes("daily_reports")}

    if "report_type" not in daily_reports_columns:
        op.add_column(
            "daily_reports",
            sa.Column(
                "report_type",
                postgresql.ENUM(name="daily_report_type", create_type=False),
                nullable=False,
                server_default="ad_hoc",
                comment="日报类型(T-1301):晨规划/晚复核/其他",
            ),
        )
    if "ix_daily_reports_report_type" not in daily_reports_indexes:
        op.create_index("ix_daily_reports_report_type", "daily_reports", ["report_type"])

    if "parent_plan_id" not in daily_reports_columns:
        op.add_column(
            "daily_reports",
            sa.Column(
                "parent_plan_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="晚复核引用的晨规划日报 ID(T-1301)",
            ),
        )
        op.create_foreign_key(
            "fk_daily_reports_parent_plan_id",
            "daily_reports",
            "daily_reports",
            ["parent_plan_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "ix_daily_reports_parent_plan_id" not in daily_reports_indexes:
        op.create_index("ix_daily_reports_parent_plan_id", "daily_reports", ["parent_plan_id"])

    if "planned_status" not in daily_reports_columns:
        op.add_column(
            "daily_reports",
            sa.Column(
                "planned_status",
                postgresql.ENUM(name="daily_report_planned_status", create_type=False),
                nullable=True,
                comment="复核结果状态(T-1301)",
            ),
        )
    if "ix_daily_reports_planned_status" not in daily_reports_indexes:
        op.create_index("ix_daily_reports_planned_status", "daily_reports", ["planned_status"])

    if "work_tags" not in daily_reports_columns:
        op.add_column(
            "daily_reports",
            sa.Column(
                "work_tags",
                postgresql.ARRAY(sa.String()),
                nullable=True,
                server_default="{}",
                comment="工作类型固化标签数组(T-1301)",
            ),
        )

    op.execute(
        sa.text(
            """
            UPDATE daily_reports
               SET report_type = 'morning_plan'
             WHERE raw_input_text LIKE '[晨规划]%%'
               AND report_type = 'ad_hoc'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE daily_reports
               SET report_type = 'evening_review'
             WHERE raw_input_text LIKE '[晚复盘]%%'
               AND report_type = 'ad_hoc'
            """
        )
    )
    morning_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM daily_reports WHERE report_type='morning_plan'")
    ).scalar() or 0
    evening_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM daily_reports WHERE report_type='evening_review'")
    ).scalar() or 0
    ad_hoc_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM daily_reports WHERE report_type='ad_hoc'")
    ).scalar() or 0
    print(
        "[T-1301 backfill] "
        f"morning_plan={morning_count} / evening_review={evening_count} / ad_hoc={ad_hoc_count}"
    )

    if "daily_supervised_tasks" not in inspector.get_table_names():
        op.create_table(
            "daily_supervised_tasks",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("sprint_task_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_report_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_followup_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(name="supervised_status", create_type=False),
                nullable=False,
                server_default="open",
            ),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_by_report_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], name="fk_supervised_tasks_user_id", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"], name="fk_supervised_tasks_project_id", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["sprint_task_id"],
                ["sprint_tasks.id"],
                name="fk_supervised_tasks_sprint_task_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["source_report_id"],
                ["daily_reports.id"],
                name="fk_supervised_tasks_source_report_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["project_followup_id"],
                ["project_follow_ups.id"],
                name="fk_supervised_tasks_project_followup_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["closed_by_report_id"],
                ["daily_reports.id"],
                name="fk_supervised_tasks_closed_by_report_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["created_by"], ["users.id"], name="fk_supervised_tasks_created_by", ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    supervised_indexes = {idx["name"] for idx in inspector.get_indexes("daily_supervised_tasks")}
    for index_name, cols in (
        ("ix_daily_supervised_tasks_user_id", ["user_id"]),
        ("ix_daily_supervised_tasks_project_id", ["project_id"]),
        ("ix_daily_supervised_tasks_source_report_id", ["source_report_id"]),
        ("ix_daily_supervised_tasks_status", ["status"]),
        ("ix_daily_supervised_tasks_tenant_id", ["tenant_id"]),
        ("ix_daily_supervised_tasks_user_status_active", ["user_id", "status", "created_at"]),
        ("ix_daily_supervised_tasks_project_status", ["project_id", "status"]),
    ):
        if index_name not in supervised_indexes:
            op.create_index(index_name, "daily_supervised_tasks", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "daily_supervised_tasks" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("daily_supervised_tasks")}
        for name in (
            "ix_daily_supervised_tasks_project_status",
            "ix_daily_supervised_tasks_user_status_active",
            "ix_daily_supervised_tasks_tenant_id",
            "ix_daily_supervised_tasks_status",
            "ix_daily_supervised_tasks_source_report_id",
            "ix_daily_supervised_tasks_project_id",
            "ix_daily_supervised_tasks_user_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="daily_supervised_tasks")
        op.drop_table("daily_supervised_tasks")

    daily_reports_columns = {column["name"] for column in inspector.get_columns("daily_reports")}
    daily_reports_indexes = {idx["name"] for idx in inspector.get_indexes("daily_reports")}

    if "work_tags" in daily_reports_columns:
        op.drop_column("daily_reports", "work_tags")
    if "planned_status" in daily_reports_columns:
        if "ix_daily_reports_planned_status" in daily_reports_indexes:
            op.drop_index("ix_daily_reports_planned_status", table_name="daily_reports")
        op.drop_column("daily_reports", "planned_status")
    if "parent_plan_id" in daily_reports_columns:
        if "ix_daily_reports_parent_plan_id" in daily_reports_indexes:
            op.drop_index("ix_daily_reports_parent_plan_id", table_name="daily_reports")
        op.drop_constraint("fk_daily_reports_parent_plan_id", "daily_reports", type_="foreignkey")
        op.drop_column("daily_reports", "parent_plan_id")
    if "report_type" in daily_reports_columns:
        if "ix_daily_reports_report_type" in daily_reports_indexes:
            op.drop_index("ix_daily_reports_report_type", table_name="daily_reports")
        op.drop_column("daily_reports", "report_type")

    existing_enums = _enum_names(bind)
    for enum_name in ("supervised_status", "daily_report_planned_status", "daily_report_type"):
        if enum_name in existing_enums:
            sa.Enum(name=enum_name).drop(bind, checkfirst=False)
