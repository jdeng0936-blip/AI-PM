"""Phase 14 T-1401: milestone + contribution points incentive module.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-05-30 17:58:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
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

    milestone_node_type = postgresql.ENUM(
        "software_req",
        "software_mvp",
        "software_validate",
        "software_launch",
        "hardware_review",
        "hardware_proto",
        "hardware_finalize",
        "temporary_done",
        "custom",
        name="milestone_node_type",
        create_type=False,
    )
    if "milestone_node_type" not in existing_enums:
        milestone_node_type.create(bind, checkfirst=False)

    milestone_status = postgresql.ENUM(
        "pending",
        "in_review",
        "approved",
        "void",
        name="milestone_status",
        create_type=False,
    )
    if "milestone_status" not in existing_enums:
        milestone_status.create(bind, checkfirst=False)

    allocation_status = postgresql.ENUM(
        "pending",
        "approved",
        "reverted",
        name="allocation_status",
        create_type=False,
    )
    if "allocation_status" not in existing_enums:
        allocation_status.create(bind, checkfirst=False)

    ledger_direction = postgresql.ENUM(
        "income",
        "refund",
        "adjustment",
        name="ledger_direction",
        create_type=False,
    )
    if "ledger_direction" not in existing_enums:
        ledger_direction.create(bind, checkfirst=False)

    member_project_role = postgresql.ENUM(
        "tech_lead",
        "owner",
        "member",
        name="member_project_role",
        create_type=False,
    )
    if "member_project_role" not in existing_enums:
        member_project_role.create(bind, checkfirst=False)

    project_member_columns = {column["name"] for column in inspector.get_columns("project_members")}
    if "member_role" not in project_member_columns:
        op.add_column(
            "project_members",
            sa.Column(
                "member_role",
                postgresql.ENUM(name="member_project_role", create_type=False),
                nullable=False,
                server_default="member",
                comment="项目角色(T-1401):tech_lead 可分 ratio,owner 可发起验收,member 默认",
            ),
        )
    project_member_indexes = {idx["name"] for idx in inspector.get_indexes("project_members")}
    if "ix_project_members_member_role" not in project_member_indexes:
        op.create_index("ix_project_members_member_role", "project_members", ["member_role"])

    result = bind.execute(sa.text("UPDATE project_members SET member_role='member' WHERE member_role IS NULL"))
    print(f"[T-1401 backfill] members_updated={result.rowcount}")

    if "project_milestones" not in inspector.get_table_names():
        op.create_table(
            "project_milestones",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "node_type",
                postgresql.ENUM(name="milestone_node_type", create_type=False),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=128), nullable=False),
            sa.Column("description", sa.String(length=512), nullable=True),
            sa.Column("node_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("initial_points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("final_points", sa.Integer(), nullable=True),
            sa.Column("adjustment_reason", sa.Text(), nullable=True),
            sa.Column("target_date", sa.Date(), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(name="milestone_status", create_type=False),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_milestones_project", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["requested_by"],
                ["users.id"],
                name="fk_milestones_requested_by",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["approved_by"],
                ["users.id"],
                name="fk_milestones_approved_by",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["created_by"],
                ["users.id"],
                name="fk_milestones_created_by",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint("initial_points >= 0", name="ck_project_milestones_initial_points_non_negative"),
            sa.CheckConstraint(
                "(status != 'approved') OR (final_points IS NOT NULL)",
                name="ck_project_milestones_approved_requires_final_points",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    milestone_indexes = {idx["name"] for idx in inspector.get_indexes("project_milestones")}
    for index_name, columns in (
        ("ix_project_milestones_project_id", ["project_id"]),
        ("ix_project_milestones_status", ["status"]),
        ("ix_project_milestones_deleted_at", ["deleted_at"]),
        ("ix_project_milestones_tenant_id", ["tenant_id"]),
        ("ix_project_milestones_project_status_order", ["project_id", "status", "node_order"]),
        ("ix_project_milestones_project_status_target", ["project_id", "status", "target_date"]),
    ):
        if index_name not in milestone_indexes:
            op.create_index(index_name, "project_milestones", columns)

    inspector = sa.inspect(bind)
    if "milestone_allocations" not in inspector.get_table_names():
        op.create_table(
            "milestone_allocations",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("contribution_ratio", sa.Numeric(5, 4), nullable=False),
            sa.Column("initial_points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("final_points", sa.Integer(), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(name="allocation_status", create_type=False),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("proposed_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revert_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(
                ["milestone_id"],
                ["project_milestones.id"],
                name="fk_allocations_milestone",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_allocations_user", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["proposed_by"],
                ["users.id"],
                name="fk_allocations_proposed_by",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["created_by"],
                ["users.id"],
                name="fk_allocations_created_by",
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "contribution_ratio >= 0 AND contribution_ratio <= 1",
                name="ck_milestone_allocations_ratio_between_0_and_1",
            ),
            sa.CheckConstraint("initial_points >= 0", name="ck_milestone_allocations_initial_points_non_negative"),
            sa.PrimaryKeyConstraint("id"),
        )

    allocation_indexes = {idx["name"] for idx in inspector.get_indexes("milestone_allocations")}
    for index_name, columns in (
        ("ix_milestone_allocations_milestone_id", ["milestone_id"]),
        ("ix_milestone_allocations_user_id", ["user_id"]),
        ("ix_milestone_allocations_status", ["status"]),
        ("ix_milestone_allocations_tenant_id", ["tenant_id"]),
        ("ix_milestone_allocations_user_status_created", ["user_id", "status", "created_at"]),
    ):
        if index_name not in allocation_indexes:
            op.create_index(index_name, "milestone_allocations", columns)
    if "ix_milestone_allocations_milestone_user_active" not in allocation_indexes:
        op.create_index(
            "ix_milestone_allocations_milestone_user_active",
            "milestone_allocations",
            ["milestone_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("status != 'reverted'"),
        )

    inspector = sa.inspect(bind)
    if "user_points_ledger" not in inspector.get_table_names():
        op.create_table(
            "user_points_ledger",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("allocation_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "direction",
                postgresql.ENUM(name="ledger_direction", create_type=False),
                nullable=False,
            ),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ledger_user", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["milestone_id"],
                ["project_milestones.id"],
                name="fk_ledger_milestone",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["allocation_id"],
                ["milestone_allocations.id"],
                name="fk_ledger_allocation",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_ledger_created_by", ondelete="SET NULL"),
            sa.CheckConstraint("amount != 0", name="ck_user_points_ledger_amount_non_zero"),
            sa.PrimaryKeyConstraint("id"),
        )

    ledger_indexes = {idx["name"] for idx in inspector.get_indexes("user_points_ledger")}
    for index_name, columns in (
        ("ix_user_points_ledger_user_id", ["user_id"]),
        ("ix_user_points_ledger_direction", ["direction"]),
        ("ix_user_points_ledger_tenant_id", ["tenant_id"]),
        ("ix_user_points_ledger_user_occurred", ["user_id", "occurred_at"]),
        ("ix_user_points_ledger_milestone_direction", ["milestone_id", "direction"]),
    ):
        if index_name not in ledger_indexes:
            op.create_index(index_name, "user_points_ledger", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "user_points_ledger" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("user_points_ledger")}
        for name in (
            "ix_user_points_ledger_milestone_direction",
            "ix_user_points_ledger_user_occurred",
            "ix_user_points_ledger_tenant_id",
            "ix_user_points_ledger_direction",
            "ix_user_points_ledger_user_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="user_points_ledger")
        op.drop_table("user_points_ledger")

    if "milestone_allocations" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("milestone_allocations")}
        for name in (
            "ix_milestone_allocations_milestone_user_active",
            "ix_milestone_allocations_user_status_created",
            "ix_milestone_allocations_tenant_id",
            "ix_milestone_allocations_status",
            "ix_milestone_allocations_user_id",
            "ix_milestone_allocations_milestone_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="milestone_allocations")
        op.drop_table("milestone_allocations")

    if "project_milestones" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("project_milestones")}
        for name in (
            "ix_project_milestones_project_status_target",
            "ix_project_milestones_project_status_order",
            "ix_project_milestones_tenant_id",
            "ix_project_milestones_deleted_at",
            "ix_project_milestones_status",
            "ix_project_milestones_project_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="project_milestones")
        op.drop_table("project_milestones")

    project_member_columns = {column["name"] for column in inspector.get_columns("project_members")}
    if "member_role" in project_member_columns:
        existing = {idx["name"] for idx in inspector.get_indexes("project_members")}
        if "ix_project_members_member_role" in existing:
            op.drop_index("ix_project_members_member_role", table_name="project_members")
        op.drop_column("project_members", "member_role")

    existing_enums = _enum_names(bind)
    for enum_name in (
        "member_project_role",
        "ledger_direction",
        "allocation_status",
        "milestone_status",
        "milestone_node_type",
    ):
        if enum_name in existing_enums:
            sa.Enum(name=enum_name).drop(bind, checkfirst=False)
