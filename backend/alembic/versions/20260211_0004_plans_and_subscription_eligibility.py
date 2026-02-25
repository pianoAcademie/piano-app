"""Add plans, entitlements and client subscriptions

Revision ID: 20260211_0004
Revises: 20260211_0003
Create Date: 2026-02-11 15:25:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260211_0004"
down_revision: Union[str, None] = "20260211_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    plan_kind = postgresql.ENUM("PACK", "SUBSCRIPTION", name="plan_kind")
    plan_kind.create(op.get_bind(), checkfirst=True)

    subscription_status = postgresql.ENUM("ACTIVE", "PAUSED", "CANCELLED", "EXPIRED", name="subscription_status")
    subscription_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM("PACK", "SUBSCRIPTION", name="plan_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("credits_count", sa.Integer(), nullable=True),
        sa.Column("monthly_price_excl_vat", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "(kind = 'PACK' and credits_count is not null and credits_count > 0) "
            "or (kind = 'SUBSCRIPTION' and monthly_price_excl_vat is not null and currency_code is not null)",
            name="ck_plans_kind_fields",
        ),
    )
    op.create_index("ix_plans_code", "plans", ["code"], unique=True)

    op.create_table(
        "plan_entitlements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("plan_id", "course_type_id", name="uq_plan_entitlements"),
    )

    op.create_table(
        "client_plan_subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("ACTIVE", "PAUSED", "CANCELLED", "EXPIRED", name="subscription_status", create_type=False),
            nullable=False,
            server_default=sa.text("'ACTIVE'::subscription_status"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credits_initial", sa.Integer(), nullable=True),
        sa.Column("credits_remaining", sa.Integer(), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("credits_initial is null or credits_initial >= 0", name="ck_sub_credits_initial_non_negative"),
        sa.CheckConstraint("credits_remaining is null or credits_remaining >= 0", name="ck_sub_credits_remaining_non_negative"),
    )
    op.create_index(
        "idx_client_plan_subscriptions_active",
        "client_plan_subscriptions",
        ["user_id", "status", "ends_at"],
        unique=False,
    )

    op.add_column("bookings", sa.Column("client_plan_subscription_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_bookings_client_plan_subscription_id",
        "bookings",
        "client_plan_subscriptions",
        ["client_plan_subscription_id"],
        ["id"],
    )

    op.execute(
        """
        INSERT INTO plans (code, name, kind, credits_count)
        VALUES
            ('PACK_5_PIANO', 'Carnet 5 cours piano', 'PACK', 5),
            ('PACK_10_MULTI', 'Carnet 10 cours multi', 'PACK', 10)
        """
    )

    op.execute(
        """
        INSERT INTO plans (code, name, kind, monthly_price_excl_vat, currency_code)
        VALUES ('SUB_MONTHLY_ONLINE', 'Abonnement mensuel online', 'SUBSCRIPTION', 120.00, 'EUR')
        """
    )

    op.execute(
        """
        INSERT INTO plan_entitlements (plan_id, course_type_id)
        SELECT p.id, ct.id
        FROM plans p
        JOIN course_types ct ON ct.code in ('PIANO_GROUP_ONSITE_1H', 'PIANO_GROUP_ONLINE_1H')
        WHERE p.code = 'PACK_5_PIANO'
        """
    )

    op.execute(
        """
        INSERT INTO plan_entitlements (plan_id, course_type_id)
        SELECT p.id, ct.id
        FROM plans p
        JOIN course_types ct ON ct.code in ('PIANO_GROUP_ONSITE_1H', 'PIANO_GROUP_ONLINE_1H', 'SOLFEGE_ONLINE_30M', 'STUDIO_REHEARSAL')
        WHERE p.code = 'PACK_10_MULTI'
        """
    )

    op.execute(
        """
        INSERT INTO plan_entitlements (plan_id, course_type_id)
        SELECT p.id, ct.id
        FROM plans p
        JOIN course_types ct ON ct.code in ('PIANO_GROUP_ONLINE_1H', 'SOLFEGE_ONLINE_30M')
        WHERE p.code = 'SUB_MONTHLY_ONLINE'
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_bookings_client_plan_subscription_id", "bookings", type_="foreignkey")
    op.drop_column("bookings", "client_plan_subscription_id")

    op.drop_index("idx_client_plan_subscriptions_active", table_name="client_plan_subscriptions")
    op.drop_table("client_plan_subscriptions")

    op.drop_table("plan_entitlements")

    op.drop_index("ix_plans_code", table_name="plans")
    op.drop_table("plans")

    subscription_status = postgresql.ENUM("ACTIVE", "PAUSED", "CANCELLED", "EXPIRED", name="subscription_status")
    subscription_status.drop(op.get_bind(), checkfirst=True)

    plan_kind = postgresql.ENUM("PACK", "SUBSCRIPTION", name="plan_kind")
    plan_kind.drop(op.get_bind(), checkfirst=True)
