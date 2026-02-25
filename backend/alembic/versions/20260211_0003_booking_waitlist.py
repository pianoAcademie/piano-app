"""Add waitlist status for bookings

Revision ID: 20260211_0003
Revises: 20260211_0002
Create Date: 2026-02-11 14:55:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260211_0003"
down_revision: Union[str, None] = "20260211_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'WAITLISTED'")
    op.create_index(
        "idx_bookings_waitlist_queue",
        "bookings",
        ["session_id", "status", "booked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_bookings_waitlist_queue", table_name="bookings")

    op.execute("ALTER TYPE booking_status RENAME TO booking_status_old")
    op.execute("CREATE TYPE booking_status AS ENUM ('BOOKED', 'CANCELLED', 'ATTENDED', 'NO_SHOW')")
    op.execute("ALTER TABLE bookings ALTER COLUMN status DROP DEFAULT")
    op.execute(
        """
        ALTER TABLE bookings
        ALTER COLUMN status TYPE booking_status
        USING (
            CASE
                WHEN status::text = 'WAITLISTED' THEN 'CANCELLED'
                ELSE status::text
            END
        )::booking_status
        """
    )
    op.execute("ALTER TABLE bookings ALTER COLUMN status SET DEFAULT 'BOOKED'::booking_status")
    op.execute("DROP TYPE booking_status_old")
