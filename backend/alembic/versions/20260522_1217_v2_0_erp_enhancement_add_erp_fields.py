"""ERP enhancement: Add material_code and po_number to risk_alerts table

Revision ID: v2_0_erp_enhancement
Revises: v2_0_baseline
Create Date: 2026-05-22 12:17:00+08:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── revision identifiers ──
revision: str = "v2_0_erp_enhancement"
down_revision: Union[str, None] = "v2_0_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def add_column_if_missing(
        table: str, column_name: str, column_def: sa.Column,
    ) -> None:
        if table not in inspector.get_table_names():
            return  # 表本身不存在，兜底跳过
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column_name in existing:
            return
        op.add_column(table, column_def)

    # 1. 补齐 material_code 列
    add_column_if_missing(
        "risk_alerts",
        "material_code",
        sa.Column("material_code", sa.String(64), nullable=True),
    )

    # 2. 补齐 po_number 列
    add_column_if_missing(
        "risk_alerts",
        "po_number",
        sa.Column("po_number", sa.String(64), nullable=True),
    )

    # 3. 补齐索引
    _ensure_index(inspector, "ix_risk_alerts_material_code", "risk_alerts", ["material_code"])
    _ensure_index(inspector, "ix_risk_alerts_po_number", "risk_alerts", ["po_number"])


def _ensure_index(inspector, name: str, table: str, columns: list[str]) -> None:
    """只在缺索引时建立"""
    if table not in inspector.get_table_names():
        return
    existing = {ix["name"] for ix in inspector.get_indexes(table)}
    if name in existing:
        return
    op.create_index(name, table, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def drop_column_if_exists(table: str, col: str) -> None:
        if table not in inspector.get_table_names():
            return
        if col not in {c["name"] for c in inspector.get_columns(table)}:
            return
        op.drop_column(table, col)

    # 1. 删索引
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("risk_alerts")} if "risk_alerts" in inspector.get_table_names() else set()
    if "ix_risk_alerts_po_number" in existing_indexes:
        op.drop_index("ix_risk_alerts_po_number", table_name="risk_alerts")
    if "ix_risk_alerts_material_code" in existing_indexes:
        op.drop_index("ix_risk_alerts_material_code", table_name="risk_alerts")

    # 2. 删列
    drop_column_if_exists("risk_alerts", "po_number")
    drop_column_if_exists("risk_alerts", "material_code")
