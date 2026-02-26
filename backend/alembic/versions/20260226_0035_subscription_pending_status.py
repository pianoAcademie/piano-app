"""add pending subscription status

Revision ID: 20260226_0035
Revises: 20260225_0034
Create Date: 2026-02-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260226_0035"
down_revision = "20260225_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PENDING'")


def downgrade() -> None:
    # PostgreSQL enum value removal is not supported safely in-place.
    pass
