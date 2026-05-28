"""Security/readiness constraints and pgvector extension guard.

Revision ID: 9a1b2c3d4e5f
Revises: b58bb129c24b
Create Date: 2026-05-28 10:00:00.000000+08:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a1b2c3d4e5f"
down_revision: Union[str, None] = "b58bb129c24b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_reports_active_idempotency
        ON daily_reports (tenant_id, user_id, report_date, md5(raw_input_text))
        WHERE deleted_at IS NULL;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_sprints_project_sprint_number'
            ) THEN
                ALTER TABLE sprints
                ADD CONSTRAINT uq_sprints_project_sprint_number
                UNIQUE (project_id, sprint_number);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE sprints
        DROP CONSTRAINT IF EXISTS uq_sprints_project_sprint_number;
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_daily_reports_active_idempotency")
