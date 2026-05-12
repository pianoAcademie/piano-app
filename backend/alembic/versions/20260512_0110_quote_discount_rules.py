"""quote discount rules

Revision ID: 20260512_0110
Revises: 20260511_0109
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260512_0110"
down_revision = "20260511_0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quote_discount_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("unit_price_ttc", sa.Numeric(12, 2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_quote_discount_rules_code"),
    )
    op.execute(
        """
        insert into quote_discount_rules (code, label, unit_price_ttc, vat_rate, currency, is_active, sort_order)
        values
          ('REMISE_FIDELITE', 'Remise fidélité', 2.00, 20.00, 'EUR', true, 10),
          ('REMISE_FAMILLE', 'Remise famille', 4.00, 20.00, 'EUR', true, 20)
        on conflict (code) do nothing
        """
    )


def downgrade() -> None:
    op.drop_table("quote_discount_rules")
