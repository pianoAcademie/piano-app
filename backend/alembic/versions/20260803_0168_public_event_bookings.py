"""allow public event bookings without an account

Revision ID: 20260803_0168
Revises: 20260803_0167
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260803_0168"
down_revision = "20260803_0167"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("school_event_registrations", "booker_user_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("school_event_registrations", sa.Column("public_booker_first_name", sa.String(100), nullable=True))
    op.add_column("school_event_registrations", sa.Column("public_booker_last_name", sa.String(100), nullable=True))
    op.add_column("school_event_registrations", sa.Column("public_booker_email", sa.String(255), nullable=True))
    op.add_column("school_event_registrations", sa.Column("public_booker_phone", sa.String(30), nullable=True))
    op.add_column("school_event_registrations", sa.Column("public_booker_language", sa.String(8), nullable=True))
    op.create_index(
        "ix_school_event_registrations_public_booker_email",
        "school_event_registrations",
        ["public_booker_email"],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM school_event_registrations WHERE booker_user_id IS NULL"
    )
    op.drop_index("ix_school_event_registrations_public_booker_email", table_name="school_event_registrations")
    op.drop_column("school_event_registrations", "public_booker_language")
    op.drop_column("school_event_registrations", "public_booker_phone")
    op.drop_column("school_event_registrations", "public_booker_email")
    op.drop_column("school_event_registrations", "public_booker_last_name")
    op.drop_column("school_event_registrations", "public_booker_first_name")
    op.alter_column("school_event_registrations", "booker_user_id", existing_type=sa.UUID(), nullable=False)
