"""normalize uninvoiced Saudi adjustments to zero VAT

Revision ID: 20260731_0164
Revises: 20260731_0163
Create Date: 2026-07-31
"""

from __future__ import annotations

from alembic import op


revision = "20260731_0164"
down_revision = "20260731_0163"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE client_manual_transactions AS transaction
        SET amount_excl_vat = transaction.total_incl_vat,
            vat_rate = 0.00,
            vat_amount = 0.00,
            updated_at = now()
        FROM users AS customer
        WHERE customer.id = transaction.user_id
          AND UPPER(transaction.transaction_type) IN ('CHARGE', 'DISCOUNT')
          AND COALESCE(
                (
                    SELECT COALESCE(
                        NULLIF(UPPER(TRIM(adult.residence_country)), ''),
                        NULLIF(UPPER(TRIM(adult.address_country)), '')
                    )
                    FROM client_family_links AS family_link
                    JOIN users AS adult ON adult.id = family_link.adult_user_id
                    WHERE family_link.child_user_id = customer.id
                    ORDER BY family_link.is_billing_recipient DESC, family_link.created_at ASC
                    LIMIT 1
                ),
                NULLIF(UPPER(TRIM(customer.residence_country)), ''),
                NULLIF(UPPER(TRIM(customer.address_country)), '')
              ) = 'SA'
          AND transaction.vat_rate <> 0.00
          AND NOT EXISTS (
                SELECT 1
                FROM client_invoice_lines AS invoice_line
                WHERE invoice_line.source = 'MANUAL'
                  AND invoice_line.source_payment_id = transaction.id
              );
        """
    )


def downgrade() -> None:
    # The prior tax breakdown cannot be reconstructed safely without changing
    # the total, so only the forward normalization is intentionally applied.
    pass
