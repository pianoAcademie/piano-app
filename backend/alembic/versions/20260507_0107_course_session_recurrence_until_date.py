"""store course session recurrence end dates

Revision ID: 20260507_0107
Revises: 20260502_0106
Create Date: 2026-05-07 10:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260507_0107"
down_revision: Union[str, None] = "20260502_0106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_sessions", sa.Column("recurrence_until_date", sa.Date(), nullable=True))

    # Existing weekly school-year series were originally generated to a date boundary
    # such as 2027-05-31, but only the generated occurrences were stored. Recreate a
    # practical boundary from the last local occurrence, with the May school-year end
    # normalized to the last day of May for editing.
    op.execute(
        """
        WITH group_bounds AS (
            SELECT
                recurrence_group_id,
                MAX((start_at_utc AT TIME ZONE COALESCE(NULLIF(timezone, ''), 'Europe/Paris'))::date) AS last_local_date
            FROM course_sessions
            WHERE recurrence_group_id IS NOT NULL
            GROUP BY recurrence_group_id
        ),
        resolved_bounds AS (
            SELECT
                recurrence_group_id,
                CASE
                    WHEN EXTRACT(MONTH FROM last_local_date) = 5
                    THEN (DATE_TRUNC('month', last_local_date)::date + INTERVAL '1 month - 1 day')::date
                    ELSE last_local_date
                END AS recurrence_until_date
            FROM group_bounds
            WHERE last_local_date IS NOT NULL
        )
        UPDATE course_sessions AS cs
        SET recurrence_until_date = rb.recurrence_until_date
        FROM resolved_bounds AS rb
        WHERE cs.recurrence_group_id = rb.recurrence_group_id
          AND cs.recurrence_until_date IS NULL
        """
    )

    # Repair recurring timed slots stored as UTC-fixed. A weekly lesson at 17:35 must
    # remain 17:35 Europe/Paris after daylight-saving changes; each occurrence keeps
    # its current local date and takes the first occurrence's local wall-clock time.
    op.execute(
        """
        WITH target_groups AS (
            SELECT
                recurrence_group_id,
                COALESCE(NULLIF((ARRAY_AGG(timezone ORDER BY start_at_utc))[1], ''), 'Europe/Paris') AS session_timezone,
                (ARRAY_AGG(start_at_utc ORDER BY start_at_utc))[1] AS anchor_start_at_utc,
                (ARRAY_AGG(end_at_utc ORDER BY start_at_utc))[1] AS anchor_end_at_utc
            FROM course_sessions
            WHERE recurrence_group_id IS NOT NULL
              AND is_all_day = FALSE
              AND recurrence_rule IS NOT NULL
              AND UPPER(recurrence_rule) NOT LIKE '%@LOCAL'
            GROUP BY recurrence_group_id
        ),
        recalculated AS (
            SELECT
                cs.id,
                (
                    (
                        (cs.start_at_utc AT TIME ZONE tg.session_timezone)::date
                        + (tg.anchor_start_at_utc AT TIME ZONE tg.session_timezone)::time
                    ) AT TIME ZONE tg.session_timezone
                ) AS next_start_at_utc,
                (
                    (
                        (cs.start_at_utc AT TIME ZONE tg.session_timezone)::date
                        + (tg.anchor_end_at_utc AT TIME ZONE tg.session_timezone)::time
                    ) AT TIME ZONE tg.session_timezone
                ) AS next_end_at_utc
            FROM course_sessions AS cs
            JOIN target_groups AS tg ON tg.recurrence_group_id = cs.recurrence_group_id
            WHERE cs.is_all_day = FALSE
        )
        UPDATE course_sessions AS cs
        SET
            start_at_utc = recalculated.next_start_at_utc,
            end_at_utc = recalculated.next_end_at_utc,
            auto_cancel_deadline_utc = recalculated.next_start_at_utc - (cs.start_at_utc - cs.auto_cancel_deadline_utc),
            recurrence_rule = CASE
                WHEN cs.recurrence_rule IS NULL THEN NULL
                WHEN POSITION('@' IN cs.recurrence_rule) > 0
                THEN REGEXP_REPLACE(cs.recurrence_rule, '@[^@]+$', '@LOCAL')
                ELSE cs.recurrence_rule || '@LOCAL'
            END,
            updated_at = NOW()
        FROM recalculated
        WHERE cs.id = recalculated.id
        """
    )


def downgrade() -> None:
    op.drop_column("course_sessions", "recurrence_until_date")
