"""Remove Sandrine duplicate credit invoice note.

Revision ID: 20260529_0142
Revises: 20260529_0141
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "20260529_0142"
down_revision = "20260529_0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TEMP TABLE tmp_sandrine_duplicate_credit_notes ON COMMIT DROP AS
        SELECT note.id, note.user_id
        FROM client_note_entries AS note
        WHERE note.message LIKE '%INVOICE_RANGE::%'
          AND note.message LIKE '%FAC-20260630-16F38D69%'
        """
    )
    op.execute(
        """
        CREATE TEMP TABLE tmp_sandrine_duplicate_credit_manuals ON COMMIT DROP AS
        SELECT DISTINCT cmt.id, cmt.user_id
        FROM client_manual_transactions AS cmt
        JOIN client_invoice_lines AS cil
          ON cil.source = 'MANUAL'
         AND cil.source_payment_id = cmt.id
        JOIN tmp_sandrine_duplicate_credit_notes AS target_note
          ON target_note.id = cil.note_id
        WHERE trim(cmt.label) = 'Avoir au 30 juin 2026 - Maxime Eurieult'
          AND cmt.total_incl_vat < 0

        UNION

        SELECT cmt.id, cmt.user_id
        FROM client_manual_transactions AS cmt
        WHERE trim(cmt.label) = 'Avoir au 30 juin 2026 - Maxime Eurieult'
          AND cmt.occurred_at >= TIMESTAMPTZ '2026-06-30 00:00:00+00'
          AND cmt.occurred_at < TIMESTAMPTZ '2026-07-01 00:00:00+00'
          AND cmt.total_incl_vat < 0
          AND upper(cmt.currency) = 'EUR'
        """
    )
    op.execute(
        """
        UPDATE client_billing_adjustments AS cba
        SET status = 'DISMISSED',
            dismissed_reason = 'Avoir doublon supprime avec la facture FAC-20260630-16F38D69 apres rollback/revalidation du devis.',
            converted_manual_transaction_id = NULL,
            decided_at = now(),
            updated_at = now()
        WHERE cba.converted_manual_transaction_id IN (
            SELECT id FROM tmp_sandrine_duplicate_credit_manuals
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
                SELECT id FROM tmp_sandrine_duplicate_credit_manuals
            )
            """
        )
    op.execute(
        """
        UPDATE referral_rewards
        SET credit_transaction_id = NULL
        WHERE credit_transaction_id IN (
            SELECT id FROM tmp_sandrine_duplicate_credit_manuals
        )
        """
    )
    op.execute(
        """
        DELETE FROM client_payment_refunds AS refund
        USING tmp_sandrine_duplicate_credit_manuals AS target
        WHERE refund.source = 'MANUAL'
          AND refund.source_payment_id = target.id
        """
    )
    op.execute(
        """
        DELETE FROM client_invoice_lines AS cil
        USING tmp_sandrine_duplicate_credit_notes AS target_note
        WHERE cil.note_id = target_note.id
        """
    )
    op.execute(
        """
        DELETE FROM client_manual_transactions AS cmt
        USING tmp_sandrine_duplicate_credit_manuals AS target
        WHERE cmt.id = target.id
        """
    )
    op.execute(
        """
        DELETE FROM client_note_entries AS note
        USING tmp_sandrine_duplicate_credit_notes AS target
        WHERE note.id = target.id
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
        FROM tmp_sandrine_duplicate_credit_manuals AS target
        """
    )


def downgrade() -> None:
    pass
