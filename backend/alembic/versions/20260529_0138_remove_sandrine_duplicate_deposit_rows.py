"""Remove Sandrine duplicate deposit rows.

Revision ID: 20260529_0138
Revises: 20260529_0137
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "20260529_0138"
down_revision = "20260529_0137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Superseded by 20260529_0139, which clears every possible reference before
    # deleting the duplicated rows.
    pass


def downgrade() -> None:
    pass
