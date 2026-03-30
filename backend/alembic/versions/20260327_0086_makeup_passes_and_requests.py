"""add makeup passes and makeup requests

Revision ID: 20260327_0086
Revises: 20260327_0085
Create Date: 2026-03-27 16:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260327_0086"
down_revision: Union[str, None] = "20260327_0085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    makeup_request_status = postgresql.ENUM("PROPOSED", "BOOKED", "EXPIRED", "CANCELLED", name="makeup_request_status")
    makeup_request_status.create(op.get_bind(), checkfirst=True)
    makeup_option_status = postgresql.ENUM("PROPOSED", "RESERVED", "UNAVAILABLE", name="makeup_option_status")
    makeup_option_status.create(op.get_bind(), checkfirst=True)

    op.add_column("catalog_products", sa.Column("is_makeup_pass", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("catalog_products", sa.Column("makeup_pass_credits", sa.Integer(), nullable=True))
    op.add_column("catalog_products", sa.Column("makeup_pass_price_first_incl_vat", sa.Numeric(12, 2), nullable=True))
    op.add_column("catalog_products", sa.Column("makeup_pass_price_next_incl_vat", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "catalog_products",
        sa.Column("makeup_pass_requires_active_forfait", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_check_constraint(
        "ck_catalog_products_makeup_pass_credits_positive",
        "catalog_products",
        "makeup_pass_credits IS NULL OR makeup_pass_credits > 0",
    )
    op.create_check_constraint(
        "ck_catalog_products_makeup_pass_price_first_non_negative",
        "catalog_products",
        "makeup_pass_price_first_incl_vat IS NULL OR makeup_pass_price_first_incl_vat >= 0",
    )
    op.create_check_constraint(
        "ck_catalog_products_makeup_pass_price_next_non_negative",
        "catalog_products",
        "makeup_pass_price_next_incl_vat IS NULL OR makeup_pass_price_next_incl_vat >= 0",
    )
    op.create_check_constraint(
        "ck_catalog_products_makeup_pass_fields",
        "catalog_products",
        "(NOT is_makeup_pass) OR (makeup_pass_credits IS NOT NULL AND makeup_pass_credits > 0 AND makeup_pass_price_first_incl_vat IS NOT NULL AND makeup_pass_price_first_incl_vat >= 0 AND makeup_pass_price_next_incl_vat IS NOT NULL AND makeup_pass_price_next_incl_vat >= 0)",
    )

    op.create_table(
        "makeup_pass_purchases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("catalog_products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "forfait_subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client_plan_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "manual_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client_manual_transactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("purchased_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("credits_initial", sa.Integer(), nullable=False),
        sa.Column("credits_remaining", sa.Integer(), nullable=False),
        sa.Column("price_incl_vat_snapshot", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("currency_snapshot", sa.Text(), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "makeup_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "forfait_subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("client_plan_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reserved_booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "used_pass_purchase_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("makeup_pass_purchases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("PROPOSED", "BOOKED", "EXPIRED", "CANCELLED", name="makeup_request_status", create_type=False),
            nullable=False,
            server_default=sa.text("'PROPOSED'::makeup_request_status"),
        ),
        sa.Column("force_without_pass", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("force_reason", sa.Text(), nullable=True),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("original_booking_id", name="uq_makeup_requests_original_booking"),
        sa.UniqueConstraint("reserved_booking_id", name="uq_makeup_requests_reserved_booking"),
    )

    op.create_table(
        "makeup_request_options",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "makeup_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("makeup_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("course_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reserved_booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "status",
            postgresql.ENUM("PROPOSED", "RESERVED", "UNAVAILABLE", name="makeup_option_status", create_type=False),
            nullable=False,
            server_default=sa.text("'PROPOSED'::makeup_option_status"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("makeup_request_id", "session_id", name="uq_makeup_request_options_request_session"),
    )

    op.add_column(
        "bookings",
        sa.Column("makeup_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("makeup_requests.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("bookings", sa.Column("makeup_credit_consumed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("bookings", sa.Column("makeup_override_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("bookings", "makeup_override_applied")
    op.drop_column("bookings", "makeup_credit_consumed")
    op.drop_column("bookings", "makeup_request_id")

    op.drop_table("makeup_request_options")
    op.drop_table("makeup_requests")
    op.drop_table("makeup_pass_purchases")

    op.drop_constraint("ck_catalog_products_makeup_pass_fields", "catalog_products", type_="check")
    op.drop_constraint("ck_catalog_products_makeup_pass_price_next_non_negative", "catalog_products", type_="check")
    op.drop_constraint("ck_catalog_products_makeup_pass_price_first_non_negative", "catalog_products", type_="check")
    op.drop_constraint("ck_catalog_products_makeup_pass_credits_positive", "catalog_products", type_="check")
    op.drop_column("catalog_products", "makeup_pass_requires_active_forfait")
    op.drop_column("catalog_products", "makeup_pass_price_next_incl_vat")
    op.drop_column("catalog_products", "makeup_pass_price_first_incl_vat")
    op.drop_column("catalog_products", "makeup_pass_credits")
    op.drop_column("catalog_products", "is_makeup_pass")

    op.execute("DROP TYPE IF EXISTS makeup_option_status")
    op.execute("DROP TYPE IF EXISTS makeup_request_status")
