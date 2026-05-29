"""Remove Sandrine duplicate credit using base label.

Revision ID: 20260529_0143
Revises: 20260529_0142
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "20260529_0143"
down_revision = "20260529_0142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TEMP TABLE tmp_sandrine_duplicate_credit_base_label ON COMMIT DROP AS
        SELECT cmt.id, cmt.user_id
        FROM client_manual_transactions AS cmt
        WHERE (
                replace(cmt.id::text, '-', '') ILIKE '16f38d69%'
                OR trim(cmt.label) IN (
                    'Avoir au 30 juin 2026',
                    'Avoir au 30 juin 2026 - Maxime Eurieult'
                )
              )
          AND cmt.occurred_at >= TIMESTAMPTZ '2026-06-30 00:00:00+00'
          AND cmt.occurred_at < TIMESTAMPTZ '2026-07-01 00:00:00+00'
          AND cmt.total_incl_vat = -200.00
          AND upper(cmt.currency) = 'EUR'
          AND (cmt.status IS NULL OR upper(cmt.status) IN ('COMPLETED', 'PAID'))
        """
    )
    op.execute(
        """
        UPDATE client_billing_adjustments AS cba
        SET status = 'DISMISSED',
            dismissed_reason = 'Avoir doublon supprime apres rollback/revalidation du devis.',
            converted_manual_transaction_id = NULL,
            decided_at = now(),
            updated_at = now()
        WHERE cba.converted_manual_transaction_id IN (
            SELECT id FROM tmp_sandrine_duplicate_credit_base_label
        )
        """
    )
    for table_name in (
        "product_requests",
        "makeup_pass_purchases",
        "payment_receipts",
        "bank_transfer_orders",
    ):
        op.execute(
            f"""
            UPDATE {table_name}
            SET manual_transaction_id = NULL
            WHERE manual_transaction_id IN (
                SELECT id FROM tmp_sandrine_duplicate_credit_base_label
            )
            """
        )
    op.execute(
        """
        UPDATE referral_rewards
        SET credit_transaction_id = NULL
        WHERE credit_transaction_id IN (
            SELECT id FROM tmp_sandrine_duplicate_credit_base_label
        )
        """
    )
    op.execute(
        """
        DELETE FROM client_payment_refunds AS refund
        USING tmp_sandrine_duplicate_credit_base_label AS target
        WHERE refund.source = 'MANUAL'
          AND refund.source_payment_id = target.id
        """
    )
    op.execute(
        """
        DELETE FROM client_invoice_lines AS cil
        USING tmp_sandrine_duplicate_credit_base_label AS target
        WHERE cil.source = 'MANUAL'
          AND cil.source_payment_id = target.id
        """
    )
    op.execute(
        """
        DELETE FROM client_manual_transactions AS cmt
        USING tmp_sandrine_duplicate_credit_base_label AS target
        WHERE cmt.id = target.id
        """
    )
    op.execute(
        """
        INSERT INTO client_note_entries (user_id, entry_type, message, created_at)
        SELECT DISTINCT
            target.user_id,
            'AUTO',
            'Avoir doublon FAC-20260630-16F38D69 supprime. Le paiement CB initial de 200 EUR est conserve.',
            now()
        FROM tmp_sandrine_duplicate_credit_base_label AS target
        """
    )


def downgrade() -> None:
    pass
