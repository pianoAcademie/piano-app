"""seed transaction product categories

Revision ID: 20260519_0127
Revises: 20260519_0126
Create Date: 2026-05-19 17:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260519_0127"
down_revision: Union[str, None] = "20260519_0126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORIES: tuple[tuple[str, str, int], ...] = (
    ("Acompte preinscription", "PRE_REGISTRATION_DEPOSIT", 10),
    ("Kit", "KIT", 20),
    ("Produit", "PRODUCT", 30),
    ("Remise", "DISCOUNT", 40),
    ("Supplement", "SURCHARGE", 50),
    ("Parrainage", "REFERRAL_CREDIT", 60),
    ("Remboursement", "BOOKING_PAYMENT_RECEIPT_REFUND", 70),
)


def upgrade() -> None:
    op.execute(
        """
        UPDATE product_categories
        SET code = 'COURSE', updated_at = now()
        WHERE name = 'Cours'
          AND code IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM product_categories existing
              WHERE existing.code = 'COURSE'
          )
        """
    )
    for name, code, display_order in CATEGORIES:
        op.execute(
            f"""
            UPDATE product_categories
            SET code = '{code}', display_order = {display_order}, updated_at = now()
            WHERE name = '{name}'
              AND code IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM product_categories existing
                  WHERE existing.code = '{code}'
              )
            """
        )
        op.execute(
            f"""
            INSERT INTO product_categories (name, code, display_order, can_be_requested_by_professor, active)
            SELECT '{name}', '{code}', {display_order}, false, true
            WHERE NOT EXISTS (
                SELECT 1 FROM product_categories
                WHERE name = '{name}' OR code = '{code}'
            )
            """
        )
    op.execute(
        """
        UPDATE client_manual_transactions
        SET category = CASE lower(category)
            WHEN 'pre_registration_deposit' THEN 'Acompte preinscription'
            WHEN 'kit' THEN 'Kit'
            WHEN 'product' THEN 'Produit'
            WHEN 'discount' THEN 'Remise'
            WHEN 'surcharge' THEN 'Supplement'
            WHEN 'off_planning_activity' THEN 'Cours'
            WHEN 'service' THEN 'Cours'
            WHEN 'quote_transformation' THEN 'Gestion'
            WHEN 'referral_credit' THEN 'Parrainage'
            WHEN 'booking_payment_receipt_refund' THEN 'Remboursement'
            ELSE category
        END,
        updated_at = now()
        WHERE transaction_type <> 'PAYMENT'
          AND category IS NOT NULL
          AND lower(category) IN (
              'pre_registration_deposit',
              'kit',
              'product',
              'discount',
              'surcharge',
              'off_planning_activity',
              'service',
              'quote_transformation',
              'referral_credit',
              'booking_payment_receipt_refund'
          )
        """
    )


def downgrade() -> None:
    codes = "', '".join(code for _, code, _ in CATEGORIES)
    op.execute(
        f"""
        DELETE FROM product_categories
        WHERE code IN ('{codes}')
          AND name IN ('{"', '".join(name for name, _, _ in CATEGORIES)}')
        """
    )
    op.execute(
        """
        UPDATE product_categories
        SET code = NULL, updated_at = now()
        WHERE name = 'Cours' AND code = 'COURSE'
        """
    )
