"""Add recurring subscription billing engine tables and fields

Revision ID: 20260312_0067
Revises: 20260312_0066
Create Date: 2026-03-12 18:45:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260312_0067"
down_revision: Union[str, None] = "20260312_0066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PAYMENT_ALERT'")
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PRE_TERMINATION'")
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'TERMINATED'")

    op.create_table(
        "subscription_retry_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("first_retry_delay_days", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_auto_attempts", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column(
            "move_to_pre_termination_after_failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_subscription_retry_policies_code"),
    )
    op.create_index(
        "ix_subscription_retry_policies_active",
        "subscription_retry_policies",
        ["active", "created_at"],
        unique=False,
    )

    op.create_table(
        "subscription_notification_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("on_success_customer_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("on_success_admin_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("on_first_failure_customer_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("on_first_failure_admin_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("on_final_failure_customer_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("on_final_failure_admin_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("customer_success_template_key", sa.String(length=120), nullable=True),
        sa.Column("admin_success_template_key", sa.String(length=120), nullable=True),
        sa.Column("customer_first_failure_template_key", sa.String(length=120), nullable=True),
        sa.Column("admin_first_failure_template_key", sa.String(length=120), nullable=True),
        sa.Column("customer_final_failure_template_key", sa.String(length=120), nullable=True),
        sa.Column("admin_final_failure_template_key", sa.String(length=120), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_subscription_notification_policies_code"),
    )
    op.create_index(
        "ix_subscription_notification_policies_active",
        "subscription_notification_policies",
        ["active", "created_at"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO subscription_retry_policies (
            code,
            name,
            first_retry_delay_days,
            max_auto_attempts,
            move_to_pre_termination_after_failed_attempts,
            active
        )
        VALUES
            ('DEFAULT_MONTHLY', 'Default monthly retry policy', 1, 2, 2, true)
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO subscription_notification_policies (
            code,
            name,
            on_success_customer_enabled,
            on_success_admin_enabled,
            on_first_failure_customer_enabled,
            on_first_failure_admin_enabled,
            on_final_failure_customer_enabled,
            on_final_failure_admin_enabled,
            active
        )
        VALUES
            ('DEFAULT_SUBSCRIPTION_NOTIFICATIONS', 'Default subscription notifications', true, true, true, true, true, true, true)
        ON CONFLICT (code) DO NOTHING
        """
    )

    op.add_column(
        "plans",
        sa.Column("billing_frequency", sa.String(length=20), nullable=False, server_default=sa.text("'monthly'")),
    )
    op.add_column("plans", sa.Column("booking_rights_policy", sa.String(length=40), nullable=True))
    op.add_column("plans", sa.Column("retry_policy_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("plans", sa.Column("notification_policy_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_plans_retry_policy_id_sub_retry_policies",
        "plans",
        "subscription_retry_policies",
        ["retry_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_plans_notification_policy_id_sub_notif_policies",
        "plans",
        "subscription_notification_policies",
        ["notification_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("client_plan_subscriptions", sa.Column("payer_contact_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "client_plan_subscriptions",
        sa.Column("bookings_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("client_plan_subscriptions", sa.Column("payment_alert_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("pre_termination_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("direct_payment_recovery_url", sa.Text(), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("last_successful_charge_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_client_plan_subscriptions_payer_contact_id_users",
        "client_plan_subscriptions",
        "users",
        ["payer_contact_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE client_plan_subscriptions
        SET current_period_start = COALESCE(current_period_start, started_at),
            current_period_end = COALESCE(current_period_end, next_payment_at, ends_at)
        """
    )

    op.create_table(
        "subscription_billing_cycles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_recovery_url", sa.Text(), nullable=True),
        sa.Column("payment_recovery_provider_ref", sa.String(length=180), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["subscription_id"], ["client_plan_subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id",
            "period_start",
            "period_end",
            name="uq_subscription_billing_cycles_subscription_period",
        ),
    )
    op.create_index(
        "ix_subscription_billing_cycles_status_billing_date",
        "subscription_billing_cycles",
        ["status", "billing_date"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_billing_cycles_status_next_retry",
        "subscription_billing_cycles",
        ["status", "next_retry_at"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_billing_cycles_subscription_id",
        "subscription_billing_cycles",
        ["subscription_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "subscription_payment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("billing_cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("provider_name", sa.String(length=60), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=180), nullable=True),
        sa.Column("provider_status", sa.String(length=80), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["billing_cycle_id"], ["subscription_billing_cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["client_plan_subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_subscription_payment_attempts_idempotency_key"),
        sa.UniqueConstraint(
            "billing_cycle_id",
            "attempt_number",
            name="uq_subscription_payment_attempts_cycle_attempt_number",
        ),
    )
    op.create_index(
        "ix_subscription_payment_attempts_subscription_attempted_at",
        "subscription_payment_attempts",
        ["subscription_id", "attempted_at"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_payment_attempts_provider_payment_id",
        "subscription_payment_attempts",
        ["provider_payment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_payment_attempts_provider_payment_id", table_name="subscription_payment_attempts")
    op.drop_index("ix_subscription_payment_attempts_subscription_attempted_at", table_name="subscription_payment_attempts")
    op.drop_table("subscription_payment_attempts")

    op.drop_index("ix_subscription_billing_cycles_subscription_id", table_name="subscription_billing_cycles")
    op.drop_index("ix_subscription_billing_cycles_status_next_retry", table_name="subscription_billing_cycles")
    op.drop_index("ix_subscription_billing_cycles_status_billing_date", table_name="subscription_billing_cycles")
    op.drop_table("subscription_billing_cycles")

    op.drop_constraint("fk_client_plan_subscriptions_payer_contact_id_users", "client_plan_subscriptions", type_="foreignkey")
    op.drop_column("client_plan_subscriptions", "current_period_end")
    op.drop_column("client_plan_subscriptions", "current_period_start")
    op.drop_column("client_plan_subscriptions", "last_successful_charge_at")
    op.drop_column("client_plan_subscriptions", "direct_payment_recovery_url")
    op.drop_column("client_plan_subscriptions", "pre_termination_at")
    op.drop_column("client_plan_subscriptions", "payment_alert_started_at")
    op.drop_column("client_plan_subscriptions", "bookings_blocked")
    op.drop_column("client_plan_subscriptions", "payer_contact_id")

    op.drop_constraint("fk_plans_notification_policy_id_sub_notif_policies", "plans", type_="foreignkey")
    op.drop_constraint("fk_plans_retry_policy_id_sub_retry_policies", "plans", type_="foreignkey")
    op.drop_column("plans", "notification_policy_id")
    op.drop_column("plans", "retry_policy_id")
    op.drop_column("plans", "booking_rights_policy")
    op.drop_column("plans", "billing_frequency")

    op.drop_index("ix_subscription_notification_policies_active", table_name="subscription_notification_policies")
    op.drop_table("subscription_notification_policies")

    op.drop_index("ix_subscription_retry_policies_active", table_name="subscription_retry_policies")
    op.drop_table("subscription_retry_policies")
