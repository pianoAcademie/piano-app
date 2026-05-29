"""Fix Castor deposit payment reconciliation.

Revision ID: 20260529_0145
Revises: 20260529_0144
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "20260529_0145"
down_revision = "20260529_0144"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            target_note_id uuid;
            target_user_id uuid;
            kept_payment_id uuid;
            removed_count integer := 0;
            invoice_payload jsonb;
            invoice_summary text;
            invoice_prefix text := 'INVOICE_RANGE::';
        BEGIN
            SELECT note.id, note.user_id
            INTO target_note_id, target_user_id
            FROM client_note_entries AS note
            WHERE note.message LIKE '%INVOICE_RANGE::%'
              AND note.message LIKE '%"invoice_number":"PA26-0110"%'
            ORDER BY note.created_at DESC, note.id DESC
            LIMIT 1;

            IF target_note_id IS NULL THEN
                RETURN;
            END IF;

            CREATE TEMP TABLE tmp_castor_deposit_payments ON COMMIT DROP AS
            SELECT
                cmt.id,
                cmt.user_id,
                cmt.occurred_at,
                cmt.created_at,
                cmt.label,
                cmt.description,
                cmt.category,
                CASE
                    WHEN upper(coalesce(cmt.category, '')) = 'INVOICE_RANGE_PUBLIC_PAYMENT' THEN 0
                    WHEN cmt.label ILIKE 'Paiement en ligne facture PA26-0110%' THEN 1
                    WHEN coalesce(cmt.reference, '') ILIKE '%PAYPLUG%' OR coalesce(cmt.reference, '') ILIKE '%MOLLIE%' THEN 2
                    WHEN cmt.label ILIKE 'Paiement manuel - HUGO CASTOR%' THEN 9
                    ELSE 5
                END AS keep_rank
            FROM client_manual_transactions AS cmt
            WHERE cmt.user_id = target_user_id
              AND upper(cmt.transaction_type) = 'PAYMENT'
              AND upper(coalesce(cmt.status, 'COMPLETED')) IN ('COMPLETED', 'PAID')
              AND upper(coalesce(cmt.currency, 'EUR')) = 'EUR'
              AND cmt.total_incl_vat = -200.00
              AND (
                    cmt.label ILIKE '%PA26-0110%'
                 OR cmt.description ILIKE '%PA26-0110%'
                 OR cmt.label ILIKE '%HUGO CASTOR%'
                 OR cmt.description ILIKE '%HUGO CASTOR%'
                 OR cmt.occurred_at >= TIMESTAMPTZ '2026-05-25 00:00:00+00'
                    AND cmt.occurred_at < TIMESTAMPTZ '2026-05-26 00:00:00+00'
              );

            SELECT id
            INTO kept_payment_id
            FROM tmp_castor_deposit_payments
            ORDER BY keep_rank ASC, created_at ASC, occurred_at ASC, id ASC
            LIMIT 1;

            IF kept_payment_id IS NULL THEN
                RETURN;
            END IF;

            CREATE TEMP TABLE tmp_castor_duplicate_payments ON COMMIT DROP AS
            SELECT id
            FROM tmp_castor_deposit_payments
            WHERE id <> kept_payment_id;

            SELECT count(*) INTO removed_count FROM tmp_castor_duplicate_payments;

            IF removed_count > 0 THEN
                UPDATE client_billing_adjustments AS cba
                SET status = 'DISMISSED',
                    dismissed_reason = 'Paiement doublon Castor supprime apres rapprochement PA26-0110.',
                    converted_manual_transaction_id = NULL,
                    decided_at = now(),
                    updated_at = now()
                WHERE cba.converted_manual_transaction_id IN (
                    SELECT id FROM tmp_castor_duplicate_payments
                );

                UPDATE product_requests
                SET manual_transaction_id = NULL
                WHERE manual_transaction_id IN (SELECT id FROM tmp_castor_duplicate_payments);

                UPDATE makeup_pass_purchases
                SET manual_transaction_id = NULL
                WHERE manual_transaction_id IN (SELECT id FROM tmp_castor_duplicate_payments);

                UPDATE payment_receipts
                SET manual_transaction_id = NULL
                WHERE manual_transaction_id IN (SELECT id FROM tmp_castor_duplicate_payments);

                UPDATE bank_transfer_orders
                SET manual_transaction_id = NULL
                WHERE manual_transaction_id IN (SELECT id FROM tmp_castor_duplicate_payments);

                UPDATE referral_rewards
                SET credit_transaction_id = NULL
                WHERE credit_transaction_id IN (SELECT id FROM tmp_castor_duplicate_payments);

                DELETE FROM client_payment_refunds AS refund
                USING tmp_castor_duplicate_payments AS target
                WHERE refund.source = 'MANUAL'
                  AND refund.source_payment_id = target.id;

                DELETE FROM client_invoice_lines AS cil
                USING tmp_castor_duplicate_payments AS target
                WHERE cil.source = 'MANUAL'
                  AND cil.source_payment_id = target.id;

                DELETE FROM client_manual_transactions AS cmt
                USING tmp_castor_duplicate_payments AS target
                WHERE cmt.id = target.id;
            END IF;

            DELETE FROM client_invoice_lines
            WHERE note_id = target_note_id
              AND source = 'MANUAL'
              AND source_payment_id IN (
                    SELECT id
                    FROM tmp_castor_deposit_payments
                    WHERE id <> kept_payment_id
              );

            IF NOT EXISTS (
                SELECT 1
                FROM client_invoice_lines
                WHERE note_id = target_note_id
                  AND source = 'MANUAL'
                  AND source_payment_id = kept_payment_id
            ) THEN
                INSERT INTO client_invoice_lines (
                    note_id,
                    user_id,
                    source,
                    source_payment_id,
                    occurred_at,
                    label,
                    amount_excl_vat,
                    vat_rate,
                    vat_amount,
                    total_incl_vat,
                    currency,
                    billing_entity,
                    seller_legal_entity_id,
                    created_at
                )
                SELECT
                    target_note_id,
                    cmt.user_id,
                    'MANUAL',
                    cmt.id,
                    cmt.occurred_at,
                    cmt.label,
                    cmt.amount_excl_vat,
                    cmt.vat_rate,
                    cmt.vat_amount,
                    cmt.total_incl_vat,
                    cmt.currency,
                    coalesce((payload.data ->> 'billing_entity'), 'PIANO_ACADEMIE'),
                    nullif(payload.data ->> 'seller_legal_entity_id', '')::uuid,
                    now()
                FROM client_manual_transactions AS cmt
                CROSS JOIN LATERAL (
                    SELECT substring(note.message from position(invoice_prefix in note.message) + length(invoice_prefix))::jsonb AS data
                    FROM client_note_entries AS note
                    WHERE note.id = target_note_id
                ) AS payload
                WHERE cmt.id = kept_payment_id;
            END IF;

            SELECT
                left(note.message, position(invoice_prefix in note.message) - 1),
                substring(note.message from position(invoice_prefix in note.message) + length(invoice_prefix))::jsonb
            INTO invoice_summary, invoice_payload
            FROM client_note_entries AS note
            WHERE note.id = target_note_id;

            invoice_payload = invoice_payload
                || jsonb_build_object(
                    'invoice_status', 'PAID',
                    'payment_transaction_id', kept_payment_id::text,
                    'reconciled_manual_payment_ids', jsonb_build_array(kept_payment_id::text),
                    'payment_amount_paid', '200.00',
                    'payment_currency', 'EUR',
                    'total_to_pay_by_currency', jsonb_build_object('EUR', '0.00'),
                    'applied_payment_totals_by_currency', jsonb_build_object('EUR', '-200.00')
                );

            UPDATE client_note_entries
            SET message = invoice_summary || invoice_prefix || invoice_payload::text
            WHERE id = target_note_id;

            INSERT INTO client_note_entries (user_id, entry_type, message, created_at)
            VALUES (
                target_user_id,
                'AUTO',
                CASE
                    WHEN removed_count > 0 THEN
                        'Nettoyage PA26-0110 : paiement Castor doublon supprime, paiement conserve ' || kept_payment_id::text || '.'
                    ELSE
                        'Controle PA26-0110 : aucun doublon de paiement trouve, facture maintenue payee avec le paiement ' || kept_payment_id::text || '.'
                END,
                now()
            );
        END $$;
        """
    )


def downgrade() -> None:
    pass
