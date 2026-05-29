"""Remove Sandrine duplicate deposit rows.

Revision ID: 20260529_0138
Revises: 20260529_0137
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "20260529_0138"
down_revision = "20260529_0137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TEMP TABLE tmp_sandrine_duplicate_deposit_rows ON COMMIT DROP AS
        SELECT cmt.id
        FROM client_manual_transactions AS cmt
        LEFT JOIN users AS owner_user ON owner_user.id = cmt.user_id
        LEFT JOIN users AS student_user ON student_user.id = cmt.student_user_id
        WHERE upper(cmt.currency) = 'EUR'
          AND (
            lower(owner_user.email) = 'sandrine_mignaux@hotmail.com'
            OR (
              lower(coalesce(owner_user.first_name, '')) = 'maxime'
              AND lower(coalesce(owner_user.last_name, '')) = 'eurieult'
            )
            OR (
              lower(coalesce(student_user.first_name, '')) = 'maxime'
              AND lower(coalesce(student_user.last_name, '')) = 'eurieult'
            )
          )
          AND (
            (
              cmt.transaction_type = 'DISCOUNT'
              AND cmt.status = 'COMPLETED'
              AND cmt.total_incl_vat = -200.00
              AND cmt.label = 'Avoir au 30 juin 2026 - Maxime Eurieult'
              AND coalesce(cmt.reference, '') LIKE 'CHANGE:%'
            )
            OR (
              cmt.transaction_type = 'CHARGE'
              AND cmt.status = 'PENDING'
              AND cmt.total_incl_vat = 200.00
              AND cmt.label LIKE 'Acompte preinscription - DV-20260529064557-3592%'
              AND coalesce(cmt.reference, '') LIKE 'QUOTE:%:DEPOSIT'
            )
          )
        """
    )
    op.execute(
        """
        UPDATE client_billing_adjustments AS cba
        SET status = 'DISMISSED',
            dismissed_reason = 'Avoir/acompte doublon supprime: acompte initial deja paye avant rollback.',
            converted_manual_transaction_id = NULL,
            decided_at = now(),
            updated_at = now()
        WHERE cba.converted_manual_transaction_id IN (
            SELECT id FROM tmp_sandrine_duplicate_deposit_rows
        )
        """
    )
    op.execute(
        """
        DELETE FROM client_invoice_lines AS cil
        USING tmp_sandrine_duplicate_deposit_rows AS target
        WHERE cil.source = 'MANUAL'
          AND cil.source_payment_id = target.id
        """
    )
    op.execute(
        """
        DELETE FROM client_manual_transactions AS cmt
        USING tmp_sandrine_duplicate_deposit_rows AS target
        WHERE cmt.id = target.id
        """
    )
    op.execute(
        """
        INSERT INTO client_note_entries (user_id, entry_type, message, created_at)
        SELECT
            u.id,
            'AUTO',
            'Nettoyage dossier Sandrine Mignaux: suppression de l avoir doublon et de l acompte recree apres rollback. Le paiement CB initial de 200 EUR est conserve.',
            now()
        FROM users AS u
        WHERE lower(u.email) = 'sandrine_mignaux@hotmail.com'
          AND EXISTS (SELECT 1 FROM tmp_sandrine_duplicate_deposit_rows)
        LIMIT 1
        """
    )


def downgrade() -> None:
    pass
