"""Add EXCUSED_ABSENCE booking status

Revision ID: 20260211_0007
Revises: 20260211_0006
Create Date: 2026-02-11 17:20:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260211_0007"
down_revision: Union[str, None] = "20260211_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'EXCUSED_ABSENCE'")


def downgrade() -> None:
    op.execute("ALTER TABLE bookings ALTER COLUMN status DROP DEFAULT")
    op.execute("UPDATE bookings SET status = 'NO_SHOW' WHERE status::text = 'EXCUSED_ABSENCE'")
    op.execute("ALTER TYPE booking_status RENAME TO booking_status_old")
    op.execute("CREATE TYPE booking_status AS ENUM ('BOOKED', 'WAITLISTED', 'CANCELLED', 'ATTENDED', 'NO_SHOW')")
    op.execute("ALTER TABLE bookings ALTER COLUMN status TYPE booking_status USING status::text::booking_status")
    op.execute("ALTER TABLE bookings ALTER COLUMN status SET DEFAULT 'BOOKED'::booking_status")
    op.execute("DROP TYPE booking_status_old")
