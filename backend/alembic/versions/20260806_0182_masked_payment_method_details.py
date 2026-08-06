"""Store non-sensitive payment method display details.

Revision ID: 20260806_0182
Revises: 20260805_0181
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_0182"
down_revision = "20260805_0181"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_plan_subscriptions", sa.Column("payment_method_type", sa.String(length=30), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("payment_method_brand", sa.String(length=40), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("payment_method_last4", sa.String(length=4), nullable=True))
    op.create_check_constraint(
        "ck_client_plan_subscriptions_payment_method_last4",
        "client_plan_subscriptions",
        "payment_method_last4 is null or payment_method_last4 ~ '^[0-9]{4}$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_client_plan_subscriptions_payment_method_last4",
        "client_plan_subscriptions",
        type_="check",
    )
    op.drop_column("client_plan_subscriptions", "payment_method_last4")
    op.drop_column("client_plan_subscriptions", "payment_method_brand")
    op.drop_column("client_plan_subscriptions", "payment_method_type")
