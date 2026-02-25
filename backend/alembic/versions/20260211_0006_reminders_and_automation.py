"""Add reminders and automation settings

Revision ID: 20260211_0006
Revises: 20260211_0005
Create Date: 2026-02-11 16:45:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260211_0006"
down_revision: Union[str, None] = "20260211_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    reminder_status = postgresql.ENUM("PENDING", "SENT", "FAILED", "SKIPPED", name="reminder_status")
    reminder_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "email_reminders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_for_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("PENDING", "SENT", "FAILED", "SKIPPED", name="reminder_status", create_type=False),
            nullable=False,
            server_default=sa.text("'PENDING'::reminder_status"),
        ),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("booking_id", "scheduled_for_utc", name="uq_email_reminders_booking_schedule"),
    )
    op.create_index(
        "idx_email_reminders_queue",
        "email_reminders",
        ["status", "scheduled_for_utc"],
        unique=False,
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=120), primary_key=True, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES
            ('reminder_hours_before_start', '24'),
            ('auto_cancel_hours_before_start', '6')
        """
    )


def downgrade() -> None:
    op.drop_table("app_settings")

    op.drop_index("idx_email_reminders_queue", table_name="email_reminders")
    op.drop_table("email_reminders")

    reminder_status = postgresql.ENUM("PENDING", "SENT", "FAILED", "SKIPPED", name="reminder_status")
    reminder_status.drop(op.get_bind(), checkfirst=True)
