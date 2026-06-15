"""Fix Assas 2026-2027 simulation slots to Wednesday only.

Revision ID: 20260609_0150
Revises: 20260609_0149
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op


revision = "20260609_0150"
down_revision = "20260609_0149"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE course_sessions AS session
        SET status = 'CANCELLED',
            cancel_reason = 'Creneau Assas ferme: seuls les mercredis sont ouverts pour la simulation 2026-2027.',
            is_private = true,
            allow_online_booking = false,
            visibility_scope = 'PRIVATE',
            booking_scope = 'PRIVATE',
            updated_at = now()
        FROM locations AS location
        WHERE session.location_id = location.id
          AND location.code = 'ASSAS'
          AND session.status <> 'CANCELLED'
          AND session.start_at_utc >= TIMESTAMPTZ '2026-09-01 00:00:00+00'
          AND session.start_at_utc < TIMESTAMPTZ '2027-07-01 00:00:00+00'
          AND extract(isodow FROM session.start_at_utc AT TIME ZONE coalesce(nullif(session.timezone, ''), location.timezone, 'Europe/Paris')) <> 3
          AND (
                session.private_description LIKE 'PROD_CHILD_COLLECTIVE_2026_2027|onsite-child-assas-%'
             OR session.private_description LIKE 'PROD_EVEIL_MUSICAL_2026_2027|eveil-assas-%'
          )
        """
    )


def downgrade() -> None:
    pass
