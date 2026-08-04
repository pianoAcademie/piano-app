"""persist internal notes on sessions and bookings

Revision ID: 20260804_0173
Revises: 20260804_0172
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260804_0173"
down_revision = "20260804_0172"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("course_sessions", sa.Column("internal_note", sa.Text(), nullable=True))
    op.add_column("bookings", sa.Column("internal_note", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE course_sessions AS session
        SET internal_note = legacy_notes.body
        FROM (
            SELECT
                session_id,
                string_agg(trim(body), E'\n\n' ORDER BY sent_at, created_at) AS body
            FROM professor_session_messages
            WHERE subject ILIKE '%(administration)%'
              AND trim(coalesce(body, '')) <> ''
            GROUP BY session_id
        ) AS legacy_notes
        WHERE legacy_notes.session_id = session.id
          AND trim(coalesce(session.internal_note, '')) = ''
        """
    )


def downgrade() -> None:
    op.drop_column("bookings", "internal_note")
    op.drop_column("course_sessions", "internal_note")
