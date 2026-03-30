"""add responsable client status

Revision ID: 20260330_0090
Revises: 20260330_0089
Create Date: 2026-03-30 17:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260330_0090"
down_revision: Union[str, None] = "20260330_0089"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE client_status ADD VALUE IF NOT EXISTS 'RESPONSABLE'"))
    op.execute(
        sa.text(
            """
            UPDATE users AS u
            SET client_status = 'RESPONSABLE'::client_status,
                updated_at = now()
            WHERE u.role = 'client'::user_role
              AND u.client_kind = 'ADULT'::client_kind
              AND u.client_status = 'ACTIVE'::client_status
              AND u.is_active = true
              AND u.first_course_at IS NULL
              AND EXISTS (
                SELECT 1
                FROM client_family_links AS links
                WHERE links.adult_user_id = u.id
              )
              AND NOT EXISTS (
                SELECT 1
                FROM bookings AS b
                WHERE b.user_id = u.id
              )
              AND NOT EXISTS (
                SELECT 1
                FROM client_plan_subscriptions AS subs
                WHERE subs.user_id = u.id
              )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE users
            SET client_status = 'ACTIVE'::client_status,
                updated_at = now()
            WHERE client_status = 'RESPONSABLE'::client_status
            """
        )
    )
