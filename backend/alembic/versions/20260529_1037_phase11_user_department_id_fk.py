"""Phase 11 T-1104: users.department_id FK to departments (dual-track).

Revision ID: d4f7a8b9c1e2
Revises: 9a1b2c3d4e5f
Create Date: 2026-05-29 10:37:34

T-1104 双轨纯增量:
  - 新增 users.department_id UUID FK→departments.id ON DELETE SET NULL nullable=True
  - 保留 users.department VARCHAR(64) 字段不动(T-1106 才 drop)
  - 一次性 backfill:UPDATE users SET department_id = d.id FROM departments d WHERE users.department = d.name AND users.department != ''
  - 严格 LEFT JOIN:unmapped 留 NULL,输出 dry-run 报告(N unmapped 部门名 + M 受影响 user)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision = "d4f7a8b9c1e2"
down_revision = "9a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "department_id" not in user_columns:
        op.add_column(
            "users",
            sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("users")}
    if "fk_users_department_id_departments" not in fk_names:
        op.create_foreign_key(
            "fk_users_department_id_departments",
            "users",
            "departments",
            ["department_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute("CREATE INDEX IF NOT EXISTS ix_users_department_id ON users (department_id)")

    result = bind.execute(
        sa.text(
            "UPDATE users SET department_id = d.id "
            "FROM departments d "
            "WHERE users.department = d.name "
            "AND users.tenant_id = d.tenant_id "
            "AND users.department != '' "
            "AND users.department_id IS NULL"
        )
    )
    backfilled_count = result.rowcount

    unmapped_rows = bind.execute(
        sa.text(
            "SELECT users.department AS dept_name, COUNT(*) AS user_count "
            "FROM users "
            "LEFT JOIN departments d ON users.department = d.name AND users.tenant_id = d.tenant_id "
            "WHERE users.department != '' AND d.id IS NULL "
            "GROUP BY users.department "
            "ORDER BY user_count DESC"
        )
    ).fetchall()

    print(f"[T-1104 backfill] {backfilled_count} users mapped to department_id")
    if unmapped_rows:
        print(f"[T-1104 backfill] {len(unmapped_rows)} unmapped department names:")
        for row in unmapped_rows:
            print(f"  - {row.dept_name!r}: {row.user_count} users")
    else:
        print("[T-1104 backfill] all non-empty department strings successfully mapped")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_department_id")
    op.drop_constraint("fk_users_department_id_departments", "users", type_="foreignkey")
    op.drop_column("users", "department_id")
