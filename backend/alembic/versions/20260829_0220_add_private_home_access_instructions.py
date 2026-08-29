"""Add private home access instructions to client profiles.

Revision ID: 20260829_0220
Revises: 20260828_0219
Create Date: 2026-08-29 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260829_0220"
down_revision = "20260828_0219"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("home_access_instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "home_access_instructions")
