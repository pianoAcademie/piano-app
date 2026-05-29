"""Remove duplicate Sandrine Mignaux credit note.

Revision ID: 20260529_0137
Revises: 20260527_0136
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "20260529_0137"
down_revision = "20260527_0136"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TEMP TABLE tmp_sandrine_duplicate_credit ON COMMIT DROP AS
        SELECT cmt.id, cmt.user_id
        FROM client_manual_transactions AS cmt
        JOIN users AS u ON u.id = cmt.user_id
        WHERE lower(u.email) = 'sandrine_mignaux@hotmail.com'
          AND cmt.transaction_type = 'DISCOUNT'
          AND cmt.status = 'COMPLETED'
          AND cmt.total_incl_vat = -200.00
          AND upper(cmt.currency) = 'EUR'
          AND cmt.label = 'Avoir au 30 juin 2026 - Maxime Eurieult'
          AND coalesce(cmt.reference, '') LIKE 'CHANGE:%'
        """
    )
    op.execute(
        """
        UPDATE client_billing_adjustments AS cba
        SET status = 'DISMISSED',
            dismissed_reason = 'Avoir supprime: acompte deja conserve apres rollback/revalidation du devis.',
            converted_manual_transaction_id = NULL,
            decided_at = now(),
            updated_at = now()
        WHERE cba.converted_manual_transaction_id IN (
            SELECT id FROM tmp_sandrine_duplicate_credit
        )
        """
    )
    op.execute(
        """
        DELETE FROM client_manual_transactions AS cmt
        USING tmp_sandrine_duplicate_credit AS target
        WHERE cmt.id = target.id
        """
    )
    op.execute(
        """
        INSERT INTO client_note_entries (user_id, entry_type, message, created_at)
        SELECT DISTINCT
            target.user_id,
            'AUTO',
            'Avoir doublon de 200 EUR supprime: l acompte paye initialement est conserve pour le devis revalide.',
            now()
        FROM tmp_sandrine_duplicate_credit AS target
        """
    )


def downgrade() -> None:
    pass
