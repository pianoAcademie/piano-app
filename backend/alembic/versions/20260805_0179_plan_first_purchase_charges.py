"""add configurable first-purchase charges to formulas

Revision ID: 20260805_0179
Revises: 20260805_0178
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260805_0179"
down_revision = "20260805_0178"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("first_purchase_signup_fee_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "plans",
        sa.Column("first_purchase_partitions_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("plans", sa.Column("first_purchase_partitions_price_value", sa.Numeric(12, 2), nullable=True))

    op.add_column(
        "client_plan_subscriptions",
        sa.Column("initial_amount_excl_vat", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("initial_vat_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("initial_total_incl_vat", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("initial_currency_code", sa.String(length=3), nullable=True),
    )
    op.add_column(
        "client_plan_subscriptions",
        sa.Column(
            "initial_price_breakdown_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("first_purchase_charges_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("client_plan_subscriptions", "first_purchase_charges_applied")
    op.drop_column("client_plan_subscriptions", "initial_price_breakdown_json")
    op.drop_column("client_plan_subscriptions", "initial_currency_code")
    op.drop_column("client_plan_subscriptions", "initial_total_incl_vat")
    op.drop_column("client_plan_subscriptions", "initial_vat_amount")
    op.drop_column("client_plan_subscriptions", "initial_amount_excl_vat")
    op.drop_column("plans", "first_purchase_partitions_price_value")
    op.drop_column("plans", "first_purchase_partitions_enabled")
    op.drop_column("plans", "first_purchase_signup_fee_enabled")
