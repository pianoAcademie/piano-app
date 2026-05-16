"""Add student site to users."""

from __future__ import annotations

from typing import Union

from alembic import op


revision: str = "20260516_0115"
down_revision: Union[str, None] = "20260512_0114"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'student_site') THEN
                CREATE TYPE student_site AS ENUM ('PARIS', 'BAR_LE_DUC', 'ONLINE');
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS student_site student_site")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS student_site")
    op.execute("DROP TYPE IF EXISTS student_site")
