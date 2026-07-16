"""store Payplug recurring payment method details

Revision ID: 20260716_0157
Revises: 20260707_0156
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260716_0157"
down_revision = "20260707_0156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_plan_subscriptions", sa.Column("payment_provider_code", sa.String(length=30), nullable=True))
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("payment_provider_payment_method_ref", sa.String(length=180), nullable=True),
    )
    op.add_column("client_plan_subscriptions", sa.Column("payment_method_exp_month", sa.Integer(), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("payment_method_exp_year", sa.Integer(), nullable=True))
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("payment_method_setup_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("payment_method_setup_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_client_plan_subscriptions_payment_method_exp_month",
        "client_plan_subscriptions",
        "payment_method_exp_month is null or payment_method_exp_month between 1 and 12",
    )
    op.create_check_constraint(
        "ck_client_plan_subscriptions_payment_method_exp_year",
        "client_plan_subscriptions",
        "payment_method_exp_year is null or payment_method_exp_year between 2000 and 9999",
    )
def downgrade() -> None:
    op.drop_constraint(
        "ck_client_plan_subscriptions_payment_method_exp_year",
        "client_plan_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_client_plan_subscriptions_payment_method_exp_month",
        "client_plan_subscriptions",
        type_="check",
    )
    op.drop_column("client_plan_subscriptions", "payment_method_setup_completed_at")
    op.drop_column("client_plan_subscriptions", "payment_method_setup_required")
    op.drop_column("client_plan_subscriptions", "payment_method_exp_year")
    op.drop_column("client_plan_subscriptions", "payment_method_exp_month")
    op.drop_column("client_plan_subscriptions", "payment_provider_payment_method_ref")
    op.drop_column("client_plan_subscriptions", "payment_provider_code")
