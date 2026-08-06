"""Add subscription pause dates and cancellation request workflow.

Revision ID: 20260806_0184
Revises: 20260806_0183
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_0184"
down_revision = "20260806_0183"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_plan_subscriptions", sa.Column("suspension_start_date", sa.Date(), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("suspension_end_date", sa.Date(), nullable=True))
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("cancellation_request_status", sa.String(length=20), nullable=True),
    )
    op.add_column("client_plan_subscriptions", sa.Column("cancellation_request_note", sa.Text(), nullable=True))
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("cancellation_request_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_client_plan_subscriptions_cancellation_request_status",
        "client_plan_subscriptions",
        "cancellation_request_status is null or cancellation_request_status in ('PENDING', 'APPROVED', 'REJECTED')",
    )
    op.create_check_constraint(
        "ck_client_plan_subscriptions_suspension_dates",
        "client_plan_subscriptions",
        "suspension_start_date is null or suspension_end_date is null or suspension_end_date >= suspension_start_date",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_client_plan_subscriptions_suspension_dates",
        "client_plan_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_client_plan_subscriptions_cancellation_request_status",
        "client_plan_subscriptions",
        type_="check",
    )
    op.drop_column("client_plan_subscriptions", "cancellation_request_reviewed_at")
    op.drop_column("client_plan_subscriptions", "cancellation_request_note")
    op.drop_column("client_plan_subscriptions", "cancellation_request_status")
    op.drop_column("client_plan_subscriptions", "suspension_end_date")
    op.drop_column("client_plan_subscriptions", "suspension_start_date")
