"""track daily professor attendance reminders

Revision ID: 20260802_0165
Revises: 20260731_0164
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260802_0165"
down_revision = "20260731_0164"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "professors",
        sa.Column("last_attendance_reminder_sent_on", sa.Date(), nullable=True),
    )
    # Start the new schedule on the morning following deployment instead of
    # sending a catch-up message immediately when the worker restarts later in the day.
    op.execute(
        """
        UPDATE professors
        SET last_attendance_reminder_sent_on = timezone('Europe/Paris', now())::date;
        """
    )


def downgrade() -> None:
    op.drop_column("professors", "last_attendance_reminder_sent_on")
