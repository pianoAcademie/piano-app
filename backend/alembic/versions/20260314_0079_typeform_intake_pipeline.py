"""add typeform intake pipeline tables

Revision ID: 20260314_0079
Revises: 20260314_0078
Create Date: 2026-03-14 23:59:59
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260314_0079"
down_revision: Union[str, None] = "20260314_0078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "typeform_form_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("typeform_form_id", sa.String(length=120), nullable=False),
        sa.Column("source_code", sa.String(length=120), nullable=False),
        sa.Column("location_code", sa.String(length=80), nullable=False),
        sa.Column("school_year_label", sa.String(length=80), nullable=False),
        sa.Column("audience_segment", sa.String(length=40), nullable=False),
        sa.Column("default_quote_type", sa.String(length=40), nullable=True),
        sa.Column("default_quote_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_pricing_catalog_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_payment_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_language", sa.String(length=8), nullable=False, server_default=sa.text("'fr'")),
        sa.Column("configuration_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["default_legal_entity_id"], ["legal_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["default_location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["default_payment_plan_id"], ["payment_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["default_pricing_catalog_id"], ["pricing_catalogs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["default_quote_type_id"], ["quote_types.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_code", name="uq_typeform_form_configs_source_code"),
        sa.UniqueConstraint("typeform_form_id", name="uq_typeform_form_configs_typeform_form_id"),
    )
    op.create_index(
        "ix_typeform_form_configs_location_segment",
        "typeform_form_configs",
        ["location_code", "audience_segment"],
        unique=False,
    )

    op.create_table(
        "typeform_intakes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("form_config_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_form_id", sa.String(length=120), nullable=False),
        sa.Column("source_response_id", sa.String(length=160), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("normalized_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("simplified_response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("resolution_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("blocking_reasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("intake_status", sa.String(length=40), nullable=False, server_default=sa.text("'NEW'")),
        sa.Column("detected_location", sa.String(length=80), nullable=True),
        sa.Column("detected_segment", sa.String(length=40), nullable=True),
        sa.Column("detected_school_year", sa.String(length=80), nullable=True),
        sa.Column("related_quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["form_config_id"], ["typeform_form_configs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_quote_id"], ["quotes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_form_id", "source_response_id", name="uq_typeform_intakes_source_response"),
    )
    op.create_index("ix_typeform_intakes_form_config_id", "typeform_intakes", ["form_config_id"], unique=False)
    op.create_index("ix_typeform_intakes_received_at", "typeform_intakes", ["received_at"], unique=False)
    op.create_index("ix_typeform_intakes_related_quote_id", "typeform_intakes", ["related_quote_id"], unique=False)
    op.create_index("ix_typeform_intakes_status", "typeform_intakes", ["intake_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_typeform_intakes_status", table_name="typeform_intakes")
    op.drop_index("ix_typeform_intakes_related_quote_id", table_name="typeform_intakes")
    op.drop_index("ix_typeform_intakes_received_at", table_name="typeform_intakes")
    op.drop_index("ix_typeform_intakes_form_config_id", table_name="typeform_intakes")
    op.drop_table("typeform_intakes")

    op.drop_index("ix_typeform_form_configs_location_segment", table_name="typeform_form_configs")
    op.drop_table("typeform_form_configs")
