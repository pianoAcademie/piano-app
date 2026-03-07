"""add quote document engine foundation

Revision ID: 20260313_0072
Revises: 20260313_0071
Create Date: 2026-03-13 16:20:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260313_0072"
down_revision: Union[str, None] = "20260313_0071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quote_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("template_type", sa.String(length=40), nullable=False, server_default=sa.text("'quote_body'")),
        sa.Column("target", sa.String(length=40), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False, server_default=sa.text("'fr'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_quote_templates_code"),
    )

    op.create_table(
        "quote_template_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active_version", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["quote_template_id"], ["quote_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_template_id", "version_number", name="uq_quote_template_versions_number"),
    )
    op.create_index("ix_quote_template_versions_template", "quote_template_versions", ["quote_template_id", "version_number"])

    op.create_table(
        "terms_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("terms_type", sa.String(length=40), nullable=False, server_default=sa.text("'cgv'")),
        sa.Column("target", sa.String(length=40), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False, server_default=sa.text("'fr'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_terms_templates_code"),
    )

    op.create_table(
        "terms_template_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("terms_template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active_version", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["terms_template_id"], ["terms_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("terms_template_id", "version_number", name="uq_terms_template_versions_number"),
    )
    op.create_index("ix_terms_template_versions_template", "terms_template_versions", ["terms_template_id", "version_number"])

    op.create_table(
        "quote_document_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("prospect_type", sa.String(length=20), nullable=True),
        sa.Column("context_type", sa.String(length=30), nullable=True),
        sa.Column("activity_family", sa.String(length=80), nullable=True),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("quote_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote_template_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("terms_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("terms_template_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["activity_id"], ["course_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_type_id"], ["quote_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_template_id"], ["quote_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_template_version_id"], ["quote_template_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["terms_template_id"], ["terms_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["terms_template_version_id"], ["terms_template_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prospect_type",
            "context_type",
            "activity_family",
            "language",
            "is_active",
            name="uq_quote_document_bindings_scope",
        ),
    )
    op.create_index("ix_quote_document_bindings_priority", "quote_document_bindings", ["is_active", "priority"])

    op.add_column("quotes", sa.Column("quote_template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("quotes", sa.Column("quote_template_version_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("quotes", sa.Column("terms_template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("quotes", sa.Column("terms_template_version_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("quotes", sa.Column("language", sa.String(length=8), nullable=True))
    op.add_column("quotes", sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True))
    op.add_column("quotes", sa.Column("document_status", sa.String(length=20), nullable=False, server_default=sa.text("'stale'")))
    op.add_column("quotes", sa.Column("document_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("quotes", sa.Column("document_hash", sa.String(length=120), nullable=True))
    op.add_column("quotes", sa.Column("document_generated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key("fk_quotes_quote_template_id", "quotes", "quote_templates", ["quote_template_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_quotes_quote_template_version_id", "quotes", "quote_template_versions", ["quote_template_version_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_quotes_terms_template_id", "quotes", "terms_templates", ["terms_template_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_quotes_terms_template_version_id", "quotes", "terms_template_versions", ["terms_template_version_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_quotes_document_status", "quotes", ["document_status", "updated_at"])

    op.create_table(
        "quote_document_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_kind", sa.String(length=30), nullable=False, server_default=sa.text("'combined'")),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("quote_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote_template_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("terms_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("terms_template_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote_body_snapshot", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("terms_body_snapshot", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("combined_html_snapshot", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("document_hash", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_template_id"], ["quote_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_template_version_id"], ["quote_template_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["terms_template_id"], ["terms_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["terms_template_version_id"], ["terms_template_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", "snapshot_kind", "document_hash", name="uq_quote_document_snapshots_hash"),
    )
    op.create_index("ix_quote_document_snapshots_quote_created", "quote_document_snapshots", ["quote_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_quote_document_snapshots_quote_created", table_name="quote_document_snapshots")
    op.drop_table("quote_document_snapshots")

    op.drop_index("ix_quotes_document_status", table_name="quotes")
    op.drop_constraint("fk_quotes_terms_template_version_id", "quotes", type_="foreignkey")
    op.drop_constraint("fk_quotes_terms_template_id", "quotes", type_="foreignkey")
    op.drop_constraint("fk_quotes_quote_template_version_id", "quotes", type_="foreignkey")
    op.drop_constraint("fk_quotes_quote_template_id", "quotes", type_="foreignkey")
    op.drop_column("quotes", "document_generated_at")
    op.drop_column("quotes", "document_hash")
    op.drop_column("quotes", "document_snapshot_id")
    op.drop_column("quotes", "document_status")
    op.drop_column("quotes", "vat_rate")
    op.drop_column("quotes", "language")
    op.drop_column("quotes", "terms_template_version_id")
    op.drop_column("quotes", "terms_template_id")
    op.drop_column("quotes", "quote_template_version_id")
    op.drop_column("quotes", "quote_template_id")

    op.drop_index("ix_quote_document_bindings_priority", table_name="quote_document_bindings")
    op.drop_table("quote_document_bindings")

    op.drop_index("ix_terms_template_versions_template", table_name="terms_template_versions")
    op.drop_table("terms_template_versions")

    op.drop_table("terms_templates")

    op.drop_index("ix_quote_template_versions_template", table_name="quote_template_versions")
    op.drop_table("quote_template_versions")

    op.drop_table("quote_templates")
