"""identify non-financial Sportigo opening balances

Revision ID: 20260805_0178
Revises: 20260805_0177
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260805_0178"
down_revision = "20260805_0177"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("migration_source_code", sa.String(length=60), nullable=True),
    )
    op.execute(
        """
        UPDATE client_plan_subscriptions
        SET migration_source_code = 'SPORTIGO_2026_OPENING_BALANCE'
        WHERE last_payment_status IN (
            'MIGRATED_PAYMENT_METHOD_REQUIRED',
            'MIGRATED_CREDIT_BALANCE'
        )
        """
    )


def downgrade() -> None:
    op.drop_column("client_plan_subscriptions", "migration_source_code")
