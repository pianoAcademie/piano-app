"""activate makeup pass cancellation credits

Revision ID: 20260803_0166
Revises: 20260802_0165
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260803_0166"
down_revision = "20260802_0165"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "makeup_pass_purchases",
        sa.Column("source_quote_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "makeup_pass_purchases",
        sa.Column("source_quote_line_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_makeup_pass_purchases_source_quote",
        "makeup_pass_purchases",
        "quotes",
        ["source_quote_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_makeup_pass_purchases_source_quote_line",
        "makeup_pass_purchases",
        "quote_lines",
        ["source_quote_line_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_makeup_pass_purchases_source_quote_line",
        "makeup_pass_purchases",
        ["source_quote_line_id"],
    )

    # Existing Pass Récup products predate the operational credit ledger.
    op.execute(
        """
        UPDATE catalog_products
        SET is_makeup_pass = true,
            makeup_pass_credits = COALESCE(makeup_pass_credits, 4),
            makeup_pass_price_first_incl_vat = COALESCE(makeup_pass_price_first_incl_vat, price_incl_vat, 0),
            makeup_pass_price_next_incl_vat = COALESCE(makeup_pass_price_next_incl_vat, price_incl_vat, 0),
            makeup_pass_requires_active_forfait = true,
            updated_at = now()
        WHERE lower(title) LIKE '%pass%recup%'
           OR lower(title) LIKE '%pass%récup%'
        """
    )

    # Grant the four historical credits for already integrated 2026-2027 quotes.
    op.execute(
        """
        INSERT INTO makeup_pass_purchases (
            user_id,
            product_id,
            forfait_subscription_id,
            source_quote_id,
            source_quote_line_id,
            credits_initial,
            credits_remaining,
            price_incl_vat_snapshot,
            currency_snapshot,
            created_at,
            updated_at
        )
        SELECT
            COALESCE(f.target_client_id, q.client_id),
            ql.product_id,
            NULLIF(f.payload->'quote_to_enrollment_execution'->>'subscription_id', '')::uuid,
            q.id,
            ql.id,
            GREATEST(COALESCE(cp.makeup_pass_credits, 4) * GREATEST(ql.quantity::integer, 1), 1),
            GREATEST(COALESCE(cp.makeup_pass_credits, 4) * GREATEST(ql.quantity::integer, 1), 1),
            ql.amount_ttc,
            COALESCE(q.currency, 'EUR'),
            COALESCE(q.approved_at, f.updated_at, q.updated_at, now()),
            now()
        FROM quote_lines ql
        JOIN catalog_products cp ON cp.id = ql.product_id AND cp.is_makeup_pass = true
        JOIN quotes q ON q.id = ql.quote_id
        JOIN quote_acceptance_followups f ON f.quote_id = q.id AND f.status = 'completed'
        JOIN client_plan_subscriptions s
          ON s.id = NULLIF(f.payload->'quote_to_enrollment_execution'->>'subscription_id', '')::uuid
         AND s.user_id = COALESCE(f.target_client_id, q.client_id)
        JOIN plans p ON p.id = s.plan_id
        WHERE q.status = 'approved'
          AND q.school_year_label = '2026-2027'
          AND p.kind = 'FORFAIT'
          AND p.name = 'Année 2026-2027'
          AND NOT EXISTS (
              SELECT 1 FROM makeup_pass_purchases existing
              WHERE existing.source_quote_line_id = ql.id
          )
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_makeup_pass_purchases_source_quote_line",
        "makeup_pass_purchases",
        type_="unique",
    )
    op.drop_constraint(
        "fk_makeup_pass_purchases_source_quote_line",
        "makeup_pass_purchases",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_makeup_pass_purchases_source_quote",
        "makeup_pass_purchases",
        type_="foreignkey",
    )
    op.drop_column("makeup_pass_purchases", "source_quote_line_id")
    op.drop_column("makeup_pass_purchases", "source_quote_id")
