"""add quote module foundation

Revision ID: 20260313_0070
Revises: 20260312_0069
Create Date: 2026-03-13 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260313_0070"
down_revision: Union[str, None] = "20260312_0069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prospects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("linked_client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("first_name", sa.String(length=120), nullable=True),
        sa.Column("last_name", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["linked_client_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_prospects_email"),
    )
    op.create_index("ix_prospects_status", "prospects", ["status"])

    op.create_table(
        "quote_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_expiry_days", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_quote_types_code"),
    )

    op.create_table(
        "pricing_catalogs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("school_year_label", sa.String(length=40), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pricing_catalogs_effective_from", "pricing_catalogs", ["effective_from"])

    op.create_table(
        "payment_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("payment_method", sa.String(length=40), nullable=False),
        sa.Column("schedule_type", sa.String(length=40), nullable=False),
        sa.Column("schedule_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_payment_plans_code"),
    )

    op.create_table(
        "cgv_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version_label", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_label", name="uq_cgv_versions_label"),
    )

    op.create_table(
        "solfege_level_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("level_code", sa.String(length=10), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("allowed_weekdays", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("allowed_time_slots", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("modality", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("level_code", "location_id", "modality", name="uq_solfege_level_rules_scope"),
    )

    op.create_table(
        "pricing_activity_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("student_category", sa.String(length=80), nullable=True),
        sa.Column("pricing_unit", sa.String(length=30), nullable=False, server_default=sa.text("'per_session'")),
        sa.Column("unit_price_ttc", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["activity_id"], ["course_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["catalog_id"], ["pricing_catalogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_id",
            "activity_id",
            "location_id",
            "student_category",
            "pricing_unit",
            name="uq_pricing_activity_prices_scope",
        ),
    )

    op.create_table(
        "pricing_product_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_price_ttc", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["catalog_id"], ["pricing_catalogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["catalog_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_id", "product_id", name="uq_pricing_product_prices_scope"),
    )

    op.create_table(
        "pricing_kit_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_price_ttc", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["catalog_id"], ["pricing_catalogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["kit_id"], ["catalog_kits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_id", "kit_id", name="uq_pricing_kit_prices_scope"),
    )

    op.create_table(
        "quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_number", sa.String(length=80), nullable=False),
        sa.Column("context_type", sa.String(length=30), nullable=False),
        sa.Column("quote_type", sa.String(length=30), nullable=False, server_default=sa.text("'forfait'")),
        sa.Column("quote_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pricing_catalog_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'created'")),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("parent_quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("total_ttc", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("expiry_days", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("school_year_label", sa.String(length=40), nullable=True),
        sa.Column("estimated_solfege_level", sa.String(length=10), nullable=True),
        sa.Column("solfege_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("selected_solfege_slot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calendar_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payment_terms_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("cgv_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("price_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("public_token", sa.String(length=160), nullable=True),
        sa.Column("pdf_token", sa.String(length=160), nullable=True),
        sa.Column("pdf_storage_key", sa.Text(), nullable=True),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("context_type IN ('acquisition', 'active_client')", name="ck_quotes_context_type"),
        sa.ForeignKeyConstraint(["client_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_quote_id"], ["quotes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_plan_id"], ["payment_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pricing_catalog_id"], ["pricing_catalogs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_type_id"], ["quote_types.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_number", name="uq_quotes_quote_number"),
        sa.UniqueConstraint("public_token"),
        sa.UniqueConstraint("pdf_token"),
    )
    op.create_index("ix_quotes_status_expires", "quotes", ["status", "expires_at"])
    op.create_index("ix_quotes_context_status", "quotes", ["context_type", "status"])
    op.create_index("ix_quotes_client", "quotes", ["client_id"])
    op.create_index("ix_quotes_prospect", "quotes", ["prospect_id"])

    op.create_table(
        "quote_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_category", sa.String(length=20), nullable=False),
        sa.Column("line_type", sa.String(length=20), nullable=False, server_default=sa.text("'item'")),
        sa.Column("master_item_type", sa.String(length=30), nullable=True),
        sa.Column("master_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("pricing_unit", sa.String(length=20), nullable=False, server_default=sa.text("'item'")),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default=sa.text("1")),
        sa.Column("unit_price_ttc", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("amount_ttc", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("line_category IN ('service', 'product')", name="ck_quote_lines_line_category"),
        sa.CheckConstraint("line_type IN ('item', 'discount', 'surcharge')", name="ck_quote_lines_line_type"),
        sa.ForeignKeyConstraint(["activity_id"], ["course_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["kit_id"], ["catalog_kits.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["catalog_products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_lines_quote_sort", "quote_lines", ["quote_id", "sort_order"])

    op.create_table(
        "quote_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor_type", sa.String(length=40), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_events_quote_created", "quote_events", ["quote_id", "created_at"])
    op.create_index("ix_quote_events_event_type", "quote_events", ["event_type"])

    op.create_table(
        "quote_email_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("message_key", sa.String(length=200), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_key", name="uq_quote_email_outbox_message_key"),
    )
    op.create_index("ix_quote_email_outbox_quote_kind", "quote_email_outbox", ["quote_id", "kind"])

    op.create_table(
        "quote_acceptance_followups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("payment_method_status", sa.String(length=30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("solfege_slot_status", sa.String(length=30), nullable=False, server_default=sa.text("'not_applicable'")),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_client_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", name="uq_quote_acceptance_followups_quote"),
    )
    op.create_index("ix_quote_followups_status", "quote_acceptance_followups", ["status"])


def downgrade() -> None:
    op.drop_index("ix_quote_followups_status", table_name="quote_acceptance_followups")
    op.drop_table("quote_acceptance_followups")

    op.drop_index("ix_quote_email_outbox_quote_kind", table_name="quote_email_outbox")
    op.drop_table("quote_email_outbox")

    op.drop_index("ix_quote_events_event_type", table_name="quote_events")
    op.drop_index("ix_quote_events_quote_created", table_name="quote_events")
    op.drop_table("quote_events")

    op.drop_index("ix_quote_lines_quote_sort", table_name="quote_lines")
    op.drop_table("quote_lines")

    op.drop_index("ix_quotes_prospect", table_name="quotes")
    op.drop_index("ix_quotes_client", table_name="quotes")
    op.drop_index("ix_quotes_context_status", table_name="quotes")
    op.drop_index("ix_quotes_status_expires", table_name="quotes")
    op.drop_table("quotes")

    op.drop_table("pricing_kit_prices")
    op.drop_table("pricing_product_prices")
    op.drop_table("pricing_activity_prices")
    op.drop_table("solfege_level_rules")
    op.drop_table("cgv_versions")
    op.drop_table("payment_plans")
    op.drop_index("ix_pricing_catalogs_effective_from", table_name="pricing_catalogs")
    op.drop_table("pricing_catalogs")
    op.drop_table("quote_types")
    op.drop_index("ix_prospects_status", table_name="prospects")
    op.drop_table("prospects")
