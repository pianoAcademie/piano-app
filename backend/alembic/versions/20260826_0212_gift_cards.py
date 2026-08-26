"""Add secure gift cards and their audit trail.

Revision ID: 20260826_0212
Revises: 20260826_0211
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260826_0212"
down_revision = "20260826_0211"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gift_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("code_suffix", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'CREATED'"), nullable=False),
        sa.Column("source", sa.String(length=20), server_default=sa.text("'ADMIN'"), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_order_ref", sa.String(length=120), nullable=True),
        sa.Column("external_line_ref", sa.String(length=120), nullable=True),
        sa.Column("external_reference_key", sa.String(length=280), nullable=True),
        sa.Column("purchaser_name", sa.String(length=255), nullable=True),
        sa.Column("purchaser_email", sa.String(length=255), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("personal_message", sa.String(length=1000), nullable=True),
        sa.Column("face_value_ttc", sa.Numeric(precision=12, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("purchase_price_ttc", sa.Numeric(precision=12, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("discount_ttc", sa.Numeric(precision=12, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("vat_rate", sa.Numeric(precision=7, scale=3), server_default=sa.text("0"), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'EUR'"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("redeemed_for_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("terms_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('CREATED','ACTIVE','REDEEMED','EXPIRED','CANCELLED','REFUNDED','BLOCKED')",
            name="ck_gift_cards_status",
        ),
        sa.CheckConstraint(
            "source IN ('ADMIN','APP','PHYSICAL','WORDPRESS','MIGRATION')",
            name="ck_gift_cards_source",
        ),
        sa.CheckConstraint("face_value_ttc >= 0", name="ck_gift_cards_face_value_non_negative"),
        sa.CheckConstraint("purchase_price_ttc >= 0", name="ck_gift_cards_purchase_price_non_negative"),
        sa.CheckConstraint("discount_ttc >= 0", name="ck_gift_cards_discount_non_negative"),
        sa.CheckConstraint("vat_rate >= 0", name="ck_gift_cards_vat_rate_non_negative"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["redeemed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["redeemed_for_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["client_plan_subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash", name="uq_gift_cards_code_hash"),
        sa.UniqueConstraint("external_reference_key", name="uq_gift_cards_external_reference_key"),
        sa.UniqueConstraint("subscription_id", name="uq_gift_cards_subscription_id"),
    )
    op.create_index("ix_gift_cards_status", "gift_cards", ["status"])
    op.create_index("ix_gift_cards_code_suffix", "gift_cards", ["code_suffix"])
    op.create_index("ix_gift_cards_plan_id", "gift_cards", ["plan_id"])
    op.create_index("ix_gift_cards_redeemed_for_user_id", "gift_cards", ["redeemed_for_user_id"])

    op.create_table(
        "gift_card_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("gift_card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status_before", sa.String(length=20), nullable=True),
        sa.Column("status_after", sa.String(length=20), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["gift_card_id"], ["gift_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gift_card_events_gift_card_id", "gift_card_events", ["gift_card_id"])
    op.create_index("ix_gift_card_events_created_at", "gift_card_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_gift_card_events_created_at", table_name="gift_card_events")
    op.drop_index("ix_gift_card_events_gift_card_id", table_name="gift_card_events")
    op.drop_table("gift_card_events")
    op.drop_index("ix_gift_cards_redeemed_for_user_id", table_name="gift_cards")
    op.drop_index("ix_gift_cards_plan_id", table_name="gift_cards")
    op.drop_index("ix_gift_cards_code_suffix", table_name="gift_cards")
    op.drop_index("ix_gift_cards_status", table_name="gift_cards")
    op.drop_table("gift_cards")
