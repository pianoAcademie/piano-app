"""add subscription pause/cancel/billing columns

Revision ID: 20260224_0028
Revises: 20260224_0027
Create Date: 2026-02-24 19:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260224_0028"
down_revision: Union[str, None] = "20260224_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _subscription_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("client_plan_subscriptions")}


def upgrade() -> None:
    existing = _subscription_columns()
    if "billing_method_code" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("billing_method_code", sa.String(length=40), nullable=True))
    if "next_payment_at" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("next_payment_at", sa.DateTime(timezone=True), nullable=True))
    if "last_payment_at" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("last_payment_at", sa.DateTime(timezone=True), nullable=True))
    if "last_payment_status" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("last_payment_status", sa.String(length=40), nullable=True))
    if "payment_provider_subscription_ref" not in existing:
        op.add_column(
            "client_plan_subscriptions",
            sa.Column("payment_provider_subscription_ref", sa.String(length=120), nullable=True),
        )
    if "payment_provider_customer_ref" not in existing:
        op.add_column(
            "client_plan_subscriptions",
            sa.Column("payment_provider_customer_ref", sa.String(length=120), nullable=True),
        )
    if "payment_provider_mandate_ref" not in existing:
        op.add_column(
            "client_plan_subscriptions",
            sa.Column("payment_provider_mandate_ref", sa.String(length=120), nullable=True),
        )
    if "suspension_starts_at" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("suspension_starts_at", sa.DateTime(timezone=True), nullable=True))
    if "suspension_ends_at" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("suspension_ends_at", sa.DateTime(timezone=True), nullable=True))
    if "suspension_duration_value" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("suspension_duration_value", sa.Integer(), nullable=True))
    if "suspension_duration_unit" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("suspension_duration_unit", sa.String(length=10), nullable=True))
    if "cancellation_requested_at" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True))
    if "cancellation_effective_at" not in existing:
        op.add_column("client_plan_subscriptions", sa.Column("cancellation_effective_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    existing = _subscription_columns()
    if "cancellation_effective_at" in existing:
        op.drop_column("client_plan_subscriptions", "cancellation_effective_at")
    if "cancellation_requested_at" in existing:
        op.drop_column("client_plan_subscriptions", "cancellation_requested_at")
    if "suspension_duration_unit" in existing:
        op.drop_column("client_plan_subscriptions", "suspension_duration_unit")
    if "suspension_duration_value" in existing:
        op.drop_column("client_plan_subscriptions", "suspension_duration_value")
    if "suspension_ends_at" in existing:
        op.drop_column("client_plan_subscriptions", "suspension_ends_at")
    if "suspension_starts_at" in existing:
        op.drop_column("client_plan_subscriptions", "suspension_starts_at")
    if "payment_provider_subscription_ref" in existing:
        op.drop_column("client_plan_subscriptions", "payment_provider_subscription_ref")
    if "payment_provider_customer_ref" in existing:
        op.drop_column("client_plan_subscriptions", "payment_provider_customer_ref")
    if "payment_provider_mandate_ref" in existing:
        op.drop_column("client_plan_subscriptions", "payment_provider_mandate_ref")
    if "last_payment_status" in existing:
        op.drop_column("client_plan_subscriptions", "last_payment_status")
    if "last_payment_at" in existing:
        op.drop_column("client_plan_subscriptions", "last_payment_at")
    if "next_payment_at" in existing:
        op.drop_column("client_plan_subscriptions", "next_payment_at")
    if "billing_method_code" in existing:
        op.drop_column("client_plan_subscriptions", "billing_method_code")
