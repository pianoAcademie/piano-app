"""add fixed monthly card payment plan

Revision ID: 20260707_0156
Revises: 20260629_0155
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260707_0156"
down_revision = "20260629_0155"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            insert into payment_plans (
                code,
                name,
                payment_method,
                schedule_type,
                schedule_rules,
                is_active,
                created_at,
                updated_at
            )
            values (
                'CARD_MONTHLY_FIXED',
                'CB mensuel fixe',
                'CARD_MONTHLY_FIXED',
                'monthly_fixed',
                '{"installment_count": 10}'::jsonb,
                true,
                now(),
                now()
            )
            on conflict (code) do update
            set name = excluded.name,
                payment_method = excluded.payment_method,
                schedule_type = excluded.schedule_type,
                schedule_rules = excluded.schedule_rules,
                is_active = true,
                updated_at = now()
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            update payment_plans
            set is_active = false,
                updated_at = now()
            where code = 'CARD_MONTHLY_FIXED'
            """
        )
    )
