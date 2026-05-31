"""Add project contribution total points.

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-05-31 09:15:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "contribution_total_points" not in columns:
        op.add_column(
            "projects",
            sa.Column(
                "contribution_total_points",
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="项目贡献积分总额，独立于预算，不按预算自动换算",
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "contribution_total_points" in columns:
        op.drop_column("projects", "contribution_total_points")
