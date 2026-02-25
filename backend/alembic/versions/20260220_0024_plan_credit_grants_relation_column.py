"""add plan credit grants relation column

Revision ID: 20260220_0024
Revises: 20260219_0023
Create Date: 2026-02-20 14:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260220_0024"
down_revision: Union[str, None] = "20260219_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'plan_credit_grants_relation') THEN
                CREATE TYPE plan_credit_grants_relation AS ENUM ('AND', 'OR');
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        ALTER TABLE plans
        ADD COLUMN IF NOT EXISTS credit_grants_relation plan_credit_grants_relation;
        """
    )

    op.execute(
        """
        UPDATE plans
        SET credit_grants_relation = 'OR'::plan_credit_grants_relation
        WHERE credit_grants_relation IS NULL;
        """
    )

    op.execute(
        """
        ALTER TABLE plans
        ALTER COLUMN credit_grants_relation SET DEFAULT 'OR'::plan_credit_grants_relation;
        """
    )

    op.execute(
        """
        ALTER TABLE plans
        ALTER COLUMN credit_grants_relation SET NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE plans
        DROP COLUMN IF EXISTS credit_grants_relation;
        """
    )
    op.execute("DROP TYPE IF EXISTS plan_credit_grants_relation")

