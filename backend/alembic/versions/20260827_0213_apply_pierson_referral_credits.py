"""Apply the two unallocated referral credits to Pierson's annual invoice.

Revision ID: 20260827_0213
Revises: 20260826_0212
"""

from __future__ import annotations

from alembic import op


revision = "20260827_0213"
down_revision = "20260826_0212"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is deliberately fail-closed and idempotent.  It only changes the
    # active, unsent annual invoice generated from the identified Pierson quote,
    # and only when exactly two available EUR 50 referral rewards can be proved.
    op.execute(
        r"""
        DO $$
        DECLARE
            invoice_prefix constant text := 'INVOICE_RANGE::';
            target_quote_number constant text := 'DV-20260824133038-3F67';
            target_note_id uuid;
            target_user_id uuid;
            invoice_summary text;
            invoice_payload jsonb;
            candidate_count integer;
            positive_vat_rate numeric(6, 3);
            positive_vat_rate_count integer;
            target_billing_entity text;
            target_seller_legal_entity_id uuid;
            period_total numeric(12, 2);
            applied_total numeric(12, 2);
            amount_due numeric(12, 2);
            current_total numeric(12, 2);
            current_due numeric(12, 2);
            included_keys jsonb;
            credit_ids jsonb;
        BEGIN
            SELECT
                note.id,
                note.user_id,
                left(note.message, position(invoice_prefix in note.message) - 1),
                parsed.data
            INTO target_note_id, target_user_id, invoice_summary, invoice_payload
            FROM client_note_entries AS note
            CROSS JOIN LATERAL (
                SELECT CASE
                    WHEN position(invoice_prefix in note.message) > 0 THEN
                        substring(
                            note.message
                            from position(invoice_prefix in note.message) + length(invoice_prefix)
                        )::jsonb
                    ELSE NULL
                END AS data
            ) AS parsed
            WHERE parsed.data IS NOT NULL
              AND note.message LIKE '%' || target_quote_number || '%'
              AND upper(coalesce(parsed.data ->> 'invoice_status', 'ISSUED')) <> 'CANCELLED'
              AND coalesce(
                    (parsed.data ->> 'annual_invoice_auto_generated')::boolean,
                    false
                  )
            ORDER BY note.created_at DESC, note.id DESC
            LIMIT 1
            FOR UPDATE;

            IF target_note_id IS NULL THEN
                RAISE NOTICE 'Pierson referral repair skipped: active annual invoice for quote % not found.', target_quote_number;
                RETURN;
            END IF;

            IF nullif(trim(coalesce(invoice_payload ->> 'emailed_at', '')), '') IS NOT NULL
               OR nullif(trim(coalesce(invoice_payload ->> 'reminded_at', '')), '') IS NOT NULL THEN
                RAISE NOTICE 'Pierson referral repair skipped: invoice % was already emailed or reminded.',
                    invoice_payload ->> 'invoice_number';
                RETURN;
            END IF;

            current_total := coalesce((invoice_payload -> 'totals_by_currency' ->> 'EUR')::numeric, 0);
            current_due := coalesce(
                (invoice_payload -> 'total_to_pay_by_currency' ->> 'EUR')::numeric,
                current_total
            );
            IF current_total < 100 OR current_due < 100 THEN
                RAISE NOTICE 'Pierson referral repair skipped: invoice % has insufficient EUR totals (% / %).',
                    invoice_payload ->> 'invoice_number', current_total, current_due;
                RETURN;
            END IF;

            CREATE TEMP TABLE tmp_pierson_referral_credits ON COMMIT DROP AS
            SELECT tx.*
            FROM client_manual_transactions AS tx
            JOIN referral_rewards AS reward
              ON reward.credit_transaction_id = tx.id
            WHERE tx.user_id = target_user_id
              AND upper(tx.transaction_type) = 'DISCOUNT'
              AND upper(coalesce(tx.status, 'COMPLETED')) = 'COMPLETED'
              AND lower(trim(coalesce(tx.category, ''))) = 'parrainage'
              AND upper(coalesce(tx.currency, 'EUR')) = 'EUR'
              AND tx.total_incl_vat = -50.00
              AND upper(reward.status) = 'CREDIT_GRANTED'
              AND NOT EXISTS (
                    SELECT 1
                    FROM client_invoice_lines AS allocated_line
                    JOIN client_note_entries AS allocated_note
                      ON allocated_note.id = allocated_line.note_id
                    WHERE allocated_line.source = 'MANUAL'
                      AND allocated_line.source_payment_id = tx.id
                      AND allocated_note.id <> target_note_id
                      AND (
                            position(invoice_prefix in allocated_note.message) = 0
                            OR upper(coalesce(
                                CASE
                                    WHEN position(invoice_prefix in allocated_note.message) > 0 THEN
                                        substring(
                                            allocated_note.message
                                            from position(invoice_prefix in allocated_note.message) + length(invoice_prefix)
                                        )::jsonb ->> 'invoice_status'
                                    ELSE NULL
                                END,
                                'ISSUED'
                            )) <> 'CANCELLED'
                      )
              )
            ORDER BY tx.occurred_at, tx.created_at, tx.id;

            SELECT count(*) INTO candidate_count FROM tmp_pierson_referral_credits;
            IF candidate_count <> 2 THEN
                RAISE NOTICE 'Pierson referral repair skipped: expected exactly 2 available EUR 50 credits, found %.',
                    candidate_count;
                RETURN;
            END IF;

            SELECT count(DISTINCT line.vat_rate), min(line.vat_rate)
            INTO positive_vat_rate_count, positive_vat_rate
            FROM client_invoice_lines AS line
            WHERE line.note_id = target_note_id
              AND upper(line.currency) = 'EUR'
              AND line.total_incl_vat > 0;

            IF positive_vat_rate_count <> 1 THEN
                RAISE NOTICE 'Pierson referral repair skipped: invoice % has % positive VAT rates.',
                    invoice_payload ->> 'invoice_number', positive_vat_rate_count;
                RETURN;
            END IF;

            SELECT line.billing_entity, line.seller_legal_entity_id
            INTO target_billing_entity, target_seller_legal_entity_id
            FROM client_invoice_lines AS line
            WHERE line.note_id = target_note_id
              AND line.total_incl_vat > 0
            ORDER BY line.created_at, line.id
            LIMIT 1;

            IF target_billing_entity IS NULL THEN
                RAISE NOTICE 'Pierson referral repair skipped: invoice % has no positive persisted line.',
                    invoice_payload ->> 'invoice_number';
                RETURN;
            END IF;

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
                target_user_id,
                'MANUAL',
                credit.id,
                credit.occurred_at,
                credit.label,
                round(credit.total_incl_vat / (1 + positive_vat_rate / 100), 2),
                positive_vat_rate,
                credit.total_incl_vat - round(credit.total_incl_vat / (1 + positive_vat_rate / 100), 2),
                credit.total_incl_vat,
                upper(coalesce(credit.currency, 'EUR')),
                target_billing_entity,
                target_seller_legal_entity_id,
                now()
            FROM tmp_pierson_referral_credits AS credit
            ON CONFLICT (note_id, source, source_payment_id) DO UPDATE
            SET amount_excl_vat = excluded.amount_excl_vat,
                vat_rate = excluded.vat_rate,
                vat_amount = excluded.vat_amount,
                total_incl_vat = excluded.total_incl_vat,
                currency = excluded.currency,
                billing_entity = excluded.billing_entity,
                seller_legal_entity_id = excluded.seller_legal_entity_id;

            SELECT coalesce(round(sum(line.total_incl_vat), 2), 0)
            INTO period_total
            FROM client_invoice_lines AS line
            WHERE line.note_id = target_note_id
              AND upper(line.currency) = 'EUR';

            applied_total := coalesce(
                (invoice_payload -> 'applied_payment_totals_by_currency' ->> 'EUR')::numeric,
                0
            );
            amount_due := greatest(round(period_total + applied_total, 2), 0);

            SELECT coalesce(jsonb_agg(to_jsonb(key_value) ORDER BY key_value), '[]'::jsonb)
            INTO included_keys
            FROM (
                SELECT DISTINCT key_value
                FROM (
                    SELECT jsonb_array_elements_text(
                        coalesce(invoice_payload -> 'included_payment_keys', '[]'::jsonb)
                    ) AS key_value
                    UNION ALL
                    SELECT 'MANUAL:' || credit.id::text
                    FROM tmp_pierson_referral_credits AS credit
                ) AS combined_keys
            ) AS unique_keys;

            SELECT jsonb_agg(to_jsonb(credit.id::text) ORDER BY credit.occurred_at, credit.created_at, credit.id)
            INTO credit_ids
            FROM tmp_pierson_referral_credits AS credit;

            invoice_payload := invoice_payload || jsonb_build_object(
                'included_payment_keys', included_keys,
                'totals_by_currency', jsonb_build_object('EUR', to_char(period_total, 'FM999999990.00')),
                'total_to_pay_by_currency', jsonb_build_object('EUR', to_char(amount_due, 'FM999999990.00')),
                'referral_credit_transaction_ids', credit_ids,
                'referral_credit_total_ttc', '100.00',
                'referral_credit_correction_applied_at', to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                'referral_credit_correction_reason', 'Two unallocated EUR 50 referral rewards applied by migration 20260827_0213'
            );

            UPDATE client_note_entries
            SET message = invoice_summary || invoice_prefix || invoice_payload::text
            WHERE id = target_note_id;

            INSERT INTO client_note_entries (user_id, entry_type, message, created_at)
            SELECT
                target_user_id,
                'AUTO',
                'Correction facture Pierson ' || coalesce(invoice_payload ->> 'invoice_number', target_note_id::text)
                    || ' : deux avoirs de parrainage de 50 EUR TTC imputes. Nouveau montant a payer : '
                    || to_char(amount_due, 'FM999999990.00') || ' EUR.',
                now()
            WHERE NOT EXISTS (
                SELECT 1
                FROM client_note_entries AS audit_note
                WHERE audit_note.user_id = target_user_id
                  AND audit_note.message LIKE 'Correction facture Pierson '
                    || coalesce(invoice_payload ->> 'invoice_number', target_note_id::text) || ' :%'
            );

            RAISE NOTICE 'Pierson referral repair applied to invoice %: EUR % -> EUR %.',
                invoice_payload ->> 'invoice_number', current_due, amount_due;
        END $$;
        """
    )


def downgrade() -> None:
    # Financial corrections are intentionally not reversed automatically.
    pass
