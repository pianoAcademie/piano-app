"""add a canonical solfege pack for migrated balances

Revision ID: 20260805_0176
Revises: 20260804_0175
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op


revision = "20260805_0176"
down_revision = "20260804_0175"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO plans (
            code,
            name,
            kind,
            credits_count,
            pack_validity_months,
            currency_code,
            description,
            billing_frequency,
            is_private,
            options_json,
            payment_methods_json,
            restrictions_json,
            active,
            updated_at
        )
        VALUES (
            'PACK_SOLFEGE_ONLINE_BALANCE',
            'Carnet de solfège en ligne',
            'PACK',
            10,
            12,
            'EUR',
            'Carnet privé utilisé pour conserver un solde de crédits de solfège déjà acquis.',
            'one_off',
            true,
            '[]'::jsonb,
            '[]'::jsonb,
            '[]'::jsonb,
            true,
            now()
        )
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            kind = EXCLUDED.kind,
            credits_count = EXCLUDED.credits_count,
            pack_validity_months = EXCLUDED.pack_validity_months,
            description = EXCLUDED.description,
            billing_frequency = EXCLUDED.billing_frequency,
            is_private = EXCLUDED.is_private,
            active = true,
            updated_at = now()
        """
    )
    op.execute(
        """
        INSERT INTO plan_credit_grants (plan_id, credit_type_id, credits_count, updated_at)
        SELECT p.id, ct.id, 10, now()
        FROM plans p
        JOIN credit_types ct ON ct.code = 'CREDIT_SOLFEGE_ONLINE'
        WHERE p.code = 'PACK_SOLFEGE_ONLINE_BALANCE'
        ON CONFLICT (plan_id, credit_type_id) DO UPDATE SET
            credits_count = EXCLUDED.credits_count,
            updated_at = now()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE plans
        SET active = false, updated_at = now()
        WHERE code = 'PACK_SOLFEGE_ONLINE_BALANCE'
        """
    )
