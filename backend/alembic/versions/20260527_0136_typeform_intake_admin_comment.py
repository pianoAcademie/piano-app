"""Add admin comment to typeform intakes.

Revision ID: 20260527_0136
Revises: 20260525_0135
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260527_0136"
down_revision = "20260525_0135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("typeform_intakes", sa.Column("admin_comment", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("typeform_intakes", "admin_comment")
