"""restore Assas collective slots cancelled by simulation cleanup

Revision ID: 20260615_0153
Revises: 20260615_0152
Create Date: 2026-06-15 17:55:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260615_0153"
down_revision: Union[str, None] = "20260615_0152"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE course_sessions AS session
        SET status = 'SCHEDULED',
            cancel_reason = NULL,
            is_private = true,
            allow_online_booking = false,
            visibility_scope = 'EXTERNAL',
            booking_scope = 'EXTERNAL',
            updated_at = now()
        FROM locations AS location
        WHERE session.location_id = location.id
          AND location.code = 'ASSAS'
          AND session.status = 'CANCELLED'
          AND session.cancel_reason = 'Creneau Assas ferme: seuls les mercredis sont ouverts pour la simulation 2026-2027.'
          AND session.start_at_utc >= TIMESTAMPTZ '2026-09-01 00:00:00+00'
          AND session.start_at_utc < TIMESTAMPTZ '2027-07-01 00:00:00+00'
          AND (
                session.private_description LIKE 'PROD_CHILD_COLLECTIVE_2026_2027|onsite-child-assas-%'
             OR session.private_description LIKE 'PROD_EVEIL_MUSICAL_2026_2027|eveil-assas-%'
          )
        """
    )


def downgrade() -> None:
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
