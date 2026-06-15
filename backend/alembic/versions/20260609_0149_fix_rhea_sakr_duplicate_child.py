"""Fix Rhea Sakr duplicate Victor Hanna child.

Revision ID: 20260609_0149
Revises: 20260605_0148
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op


revision = "20260609_0149"
down_revision = "20260605_0148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TEMP TABLE tmp_rhea_victor_child_merge ON COMMIT DROP AS
        WITH adult AS (
            SELECT id
            FROM users
            WHERE lower(email) = 'sakrrhea@gmail.com'
               OR (
                    lower(coalesce(first_name, '')) = 'rhea'
                AND lower(coalesce(last_name, '')) = 'sakr'
                AND regexp_replace(coalesce(mobile_phone_1, phone, ''), '[^0-9+]', '', 'g') IN (
                    '+33762773363',
                    '33762773363'
                )
               )
            ORDER BY (lower(email) = 'sakrrhea@gmail.com') DESC, created_at ASC
            LIMIT 1
        ),
        candidate_children AS (
            SELECT
                child.id,
                child.email,
                child.client_status,
                child.mobile_phone_1,
                child.phone,
                child.created_at,
                bool_or(link.adult_user_id = adult.id) AS linked_to_adult,
                bool_or(link.adult_user_id = adult.id AND link.is_billing_recipient) AS is_billing_recipient,
                (
                    SELECT count(*) FROM bookings AS b WHERE b.user_id = child.id
                ) + (
                    SELECT count(*) FROM client_plan_subscriptions AS cps WHERE cps.user_id = child.id
                ) + (
                    SELECT count(*) FROM client_manual_transactions AS cmt WHERE cmt.user_id = child.id OR cmt.student_user_id = child.id
                ) + (
                    SELECT count(*) FROM client_invoice_lines AS cil WHERE cil.user_id = child.id
                ) AS business_row_count
            FROM adult
            JOIN users AS child
              ON child.client_kind = 'CHILD'
             AND lower(coalesce(child.first_name, '')) = 'victor'
             AND lower(coalesce(child.last_name, '')) = 'hanna'
            LEFT JOIN client_family_links AS link
              ON link.child_user_id = child.id
            WHERE link.adult_user_id = adult.id
               OR lower(child.email) IN (
                    'child+9c63167add0442a0@piano-academie.invalid',
                    'mms-child-sdt-hlznjf@no-email.local',
                    'mms-student-bc40c7a422f94664@no-email.local',
                    'victor-hanna-ad2eff6394@presence-import.local'
               )
            GROUP BY child.id, child.email, child.client_status, child.mobile_phone_1, child.phone, child.created_at
        ),
        ranked_children AS (
            SELECT
                candidate_children.*,
                row_number() OVER (
                    ORDER BY
                        CASE
                            WHEN lower(email) LIKE 'mms-%@no-email.local'
                              OR lower(email) LIKE '%@no-email.local'
                            THEN 1 ELSE 0
                        END ASC,
                        (client_status = 'ACTIVE') DESC,
                        is_billing_recipient DESC,
                        business_row_count DESC,
                        linked_to_adult DESC,
                        created_at DESC
                ) AS rank
            FROM candidate_children
        )
        SELECT
            (SELECT id FROM adult) AS adult_id,
            canonical.id AS canonical_child_id,
            duplicate.id AS duplicate_child_id
        FROM ranked_children AS canonical
        JOIN ranked_children AS duplicate ON duplicate.rank > 1
        WHERE canonical.rank = 1
          AND (
                duplicate.linked_to_adult
             OR lower(duplicate.email) IN (
                    'mms-child-sdt-hlznjf@no-email.local',
                    'mms-student-bc40c7a422f94664@no-email.local'
                )
             OR lower(duplicate.email) LIKE 'mms-%@no-email.local'
             OR duplicate.client_status <> 'ACTIVE'
          )
        """
    )
    op.execute(
        """
        UPDATE users AS keep
        SET mobile_phone_1 = coalesce(nullif(keep.mobile_phone_1, ''), nullif(dup.mobile_phone_1, ''), nullif(adult.mobile_phone_1, '')),
            phone = coalesce(nullif(keep.phone, ''), nullif(dup.phone, ''), nullif(adult.phone, '')),
            updated_at = now()
        FROM tmp_rhea_victor_child_merge AS merge
        JOIN users AS dup ON dup.id = merge.duplicate_child_id
        JOIN users AS adult ON adult.id = merge.adult_id
        WHERE keep.id = merge.canonical_child_id
        """
    )
    op.execute(
        """
        DELETE FROM bookings AS duplicate_booking
        USING tmp_rhea_victor_child_merge AS merge
        WHERE duplicate_booking.user_id = merge.duplicate_child_id
          AND EXISTS (
              SELECT 1
              FROM bookings AS canonical_booking
              WHERE canonical_booking.session_id = duplicate_booking.session_id
                AND canonical_booking.user_id = merge.canonical_child_id
          )
        """
    )
    op.execute(
        """
        UPDATE bookings AS booking
        SET user_id = merge.canonical_child_id
        FROM tmp_rhea_victor_child_merge AS merge
        WHERE booking.user_id = merge.duplicate_child_id
        """
    )
    op.execute(
        """
        DELETE FROM client_group_memberships AS duplicate_membership
        USING tmp_rhea_victor_child_merge AS merge
        WHERE duplicate_membership.user_id = merge.duplicate_child_id
          AND EXISTS (
              SELECT 1
              FROM client_group_memberships AS canonical_membership
              WHERE canonical_membership.group_id = duplicate_membership.group_id
                AND canonical_membership.user_id = merge.canonical_child_id
          )
        """
    )
    op.execute(
        """
        UPDATE client_group_memberships AS membership
        SET user_id = merge.canonical_child_id
        FROM tmp_rhea_victor_child_merge AS merge
        WHERE membership.user_id = merge.duplicate_child_id
        """
    )
    op.execute(
        """
        UPDATE client_manual_credit_balances AS canonical_balance
        SET credits_count = canonical_balance.credits_count + duplicate_balance.credits_count,
            updated_at = now()
        FROM tmp_rhea_victor_child_merge AS merge
        JOIN client_manual_credit_balances AS duplicate_balance
          ON duplicate_balance.user_id = merge.duplicate_child_id
        WHERE canonical_balance.user_id = merge.canonical_child_id
          AND canonical_balance.credit_type_id = duplicate_balance.credit_type_id
        """
    )
    op.execute(
        """
        DELETE FROM client_manual_credit_balances AS duplicate_balance
        USING tmp_rhea_victor_child_merge AS merge
        WHERE duplicate_balance.user_id = merge.duplicate_child_id
          AND EXISTS (
              SELECT 1
              FROM client_manual_credit_balances AS canonical_balance
              WHERE canonical_balance.user_id = merge.canonical_child_id
                AND canonical_balance.credit_type_id = duplicate_balance.credit_type_id
          )
        """
    )
    op.execute(
        """
        UPDATE client_manual_credit_balances AS balance
        SET user_id = merge.canonical_child_id,
            updated_at = now()
        FROM tmp_rhea_victor_child_merge AS merge
        WHERE balance.user_id = merge.duplicate_child_id
        """
    )
    for table_name, column_name in (
        ("client_auto_invoice_rules", "user_id"),
        ("client_import_references", "user_id"),
        ("client_invoice_lines", "user_id"),
        ("client_manual_transactions", "user_id"),
        ("client_manual_transactions", "student_user_id"),
        ("client_note_entries", "user_id"),
        ("client_payment_refunds", "user_id"),
        ("client_plan_subscriptions", "user_id"),
        ("communication_logs", "recipient_user_id"),
        ("communication_logs", "sender_user_id"),
        ("makeup_pass_purchases", "user_id"),
        ("makeup_pass_purchases", "purchased_by_user_id"),
        ("makeup_requests", "user_id"),
        ("makeup_requests", "created_by_user_id"),
        ("password_reset_tokens", "user_id"),
        ("payment_receipts", "student_id"),
        ("planned_needs", "client_id"),
        ("product_requests", "student_user_id"),
        ("product_requests", "requested_by_user_id"),
        ("prospects", "linked_client_id"),
        ("quote_acceptance_followups", "target_client_id"),
        ("quotes", "client_id"),
        ("student_quote_changes", "user_id"),
        ("student_quote_changes", "student_user_id"),
    ):
        op.execute(
            f"""
            UPDATE {table_name} AS target
            SET {column_name} = merge.canonical_child_id
            FROM tmp_rhea_victor_child_merge AS merge
            WHERE target.{column_name} = merge.duplicate_child_id
            """
        )
    op.execute(
        """
        UPDATE client_family_links AS link
        SET is_billing_recipient = false,
            updated_at = now()
        FROM tmp_rhea_victor_child_merge AS merge
        WHERE link.child_user_id IN (merge.canonical_child_id, merge.duplicate_child_id)
          AND link.is_billing_recipient
        """
    )
    op.execute(
        """
        DELETE FROM client_family_links AS duplicate_link
        USING tmp_rhea_victor_child_merge AS merge
        WHERE duplicate_link.child_user_id = merge.duplicate_child_id
          AND EXISTS (
              SELECT 1
              FROM client_family_links AS canonical_link
              WHERE canonical_link.adult_user_id = duplicate_link.adult_user_id
                AND canonical_link.child_user_id = merge.canonical_child_id
          )
        """
    )
    op.execute(
        """
        UPDATE client_family_links AS link
        SET child_user_id = merge.canonical_child_id,
            updated_at = now()
        FROM tmp_rhea_victor_child_merge AS merge
        WHERE link.child_user_id = merge.duplicate_child_id
        """
    )
    op.execute(
        """
        INSERT INTO client_family_links (adult_user_id, child_user_id, relationship_label, is_billing_recipient, created_at, updated_at)
        SELECT DISTINCT adult_id, canonical_child_id, 'Parent', false, now(), now()
        FROM tmp_rhea_victor_child_merge
        ON CONFLICT ON CONSTRAINT uq_client_family_links_pair DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE client_family_links AS link
        SET is_billing_recipient = true,
            relationship_label = coalesce(nullif(link.relationship_label, ''), 'Parent'),
            updated_at = now()
        FROM tmp_rhea_victor_child_merge AS merge
        WHERE link.adult_user_id = merge.adult_id
          AND link.child_user_id = merge.canonical_child_id
        """
    )
    op.execute(
        """
        DELETE FROM users AS duplicate_child
        USING tmp_rhea_victor_child_merge AS merge
        WHERE duplicate_child.id = merge.duplicate_child_id
        """
    )
    op.execute(
        """
        UPDATE users AS adult
        SET client_status = CASE
                WHEN adult.client_status = 'ACTIVE' THEN 'RESPONSABLE'::client_status
                ELSE adult.client_status
            END,
            updated_at = now()
        FROM tmp_rhea_victor_child_merge AS merge
        WHERE adult.id = merge.adult_id
        """
    )
    op.execute(
        """
        INSERT INTO client_note_entries (user_id, entry_type, message, created_at)
        SELECT DISTINCT
            merge.canonical_child_id,
            'AUTO',
            'Doublon enfant Victor Hanna fusionne pour la famille Rhea Sakr. Le lien parent et le destinataire de facture sont conserves sur cette fiche.',
            now()
        FROM tmp_rhea_victor_child_merge AS merge
        """
    )


def downgrade() -> None:
    pass
