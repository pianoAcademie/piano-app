"""add client contact opt-ins, private notes and first course date

Revision ID: 20260215_0018
Revises: 20260215_0017
Create Date: 2026-02-15 19:18:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260215_0018"
down_revision: Union[str, None] = "20260215_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("private_note", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("first_course_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("portal_contact_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("email_opt_in", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("sms_opt_in", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("lesson_reminder_email_opt_in", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("lesson_reminder_sms_opt_in", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column(
            "communication_optout_token",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("gen_random_uuid()::text"),
        ),
    )
    op.create_index("ix_users_communication_optout_token", "users", ["communication_optout_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_communication_optout_token", table_name="users")
    op.drop_column("users", "communication_optout_token")
    op.drop_column("users", "lesson_reminder_sms_opt_in")
    op.drop_column("users", "lesson_reminder_email_opt_in")
    op.drop_column("users", "sms_opt_in")
    op.drop_column("users", "email_opt_in")
    op.drop_column("users", "portal_contact_visible")
    op.drop_column("users", "first_course_at")
    op.drop_column("users", "private_note")
