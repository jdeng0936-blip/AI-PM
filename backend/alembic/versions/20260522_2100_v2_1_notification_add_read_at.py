"""Add read_at column to notifications for in-app unread tracking

Revision ID: v2_1_notification_read_at
Revises: v2_0_erp_enhancement
Create Date: 2026-05-22 21:00:00+08:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── revision identifiers ──
revision: str = "v2_1_notification_read_at"
down_revision: Union[str, None] = "v2_0_erp_enhancement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "notifications" not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns("notifications")}
    if "read_at" not in existing_cols:
        op.add_column(
            "notifications",
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("notifications")}
    if "ix_notifications_read_at" not in existing_indexes:
        op.create_index(
            "ix_notifications_read_at",
            "notifications",
            ["read_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "notifications" not in inspector.get_table_names():
        return

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("notifications")}
    if "ix_notifications_read_at" in existing_indexes:
        op.drop_index("ix_notifications_read_at", table_name="notifications")

    existing_cols = {c["name"] for c in inspector.get_columns("notifications")}
    if "read_at" in existing_cols:
        op.drop_column("notifications", "read_at")
