"""teacher invoicing multi-entity foundations

Revision ID: 20260307_0057
Revises: 20260306_0056
Create Date: 2026-03-07 00:20:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260307_0057"
down_revision: Union[str, None] = "20260306_0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professors",
        sa.Column("teacher_invoice_counter", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "professors",
        sa.Column("teacher_is_vat_applicable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("professors", sa.Column("teacher_vat_rate", sa.Numeric(5, 2), nullable=True))
    op.add_column("professors", sa.Column("teacher_siret", sa.Text(), nullable=True))
    op.add_column("professors", sa.Column("teacher_iban", sa.Text(), nullable=True))
    op.add_column("professors", sa.Column("teacher_company_name", sa.Text(), nullable=True))
    op.add_column("professors", sa.Column("teacher_company_address", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE professors
        SET teacher_siret = nullif(trim(siret), '')
        WHERE teacher_siret IS NULL
          AND nullif(trim(siret), '') IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE professors
        SET teacher_iban = nullif(trim(iban), '')
        WHERE teacher_iban IS NULL
          AND nullif(trim(iban), '') IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE professors
        SET teacher_company_name = nullif(trim(concat_ws(' ', first_name, last_name)), '')
        WHERE teacher_company_name IS NULL
        """
    )
    op.execute(
        """
        UPDATE professors
        SET teacher_company_address = nullif(trim(address_line), '')
        WHERE teacher_company_address IS NULL
          AND nullif(trim(address_line), '') IS NOT NULL
        """
    )

    op.add_column("legal_entities", sa.Column("accounting_email", sa.Text(), nullable=True))
    op.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        SELECT 'comptability_email', 'comptabilite@piano-academie.com', now()
        WHERE NOT EXISTS (
            SELECT 1 FROM app_settings WHERE key = 'comptability_email'
        )
        """
    )

    op.add_column("course_types", sa.Column("payor_legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_course_types_payor_legal_entity_id",
        "course_types",
        "legal_entities",
        ["payor_legal_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_course_types_payor_legal_entity_id", "course_types", ["payor_legal_entity_id"], unique=False)

    op.execute(
        """
        UPDATE course_types
        SET payor_legal_entity_id = seller_legal_entity_id
        WHERE payor_legal_entity_id IS NULL
          AND seller_legal_entity_id IS NOT NULL
        """
    )
    op.execute(
        """
        WITH fallback_entity AS (
            SELECT id
            FROM legal_entities
            ORDER BY is_active DESC, created_at ASC, id ASC
            LIMIT 1
        )
        UPDATE course_types
        SET payor_legal_entity_id = (SELECT id FROM fallback_entity)
        WHERE payor_legal_entity_id IS NULL
        """
    )
    op.alter_column("course_types", "payor_legal_entity_id", nullable=False)

    op.add_column(
        "course_sessions",
        sa.Column("snapshot_payor_legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_course_sessions_snapshot_payor_legal_entity_id",
        "course_sessions",
        "legal_entities",
        ["snapshot_payor_legal_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_course_sessions_snapshot_payor_legal_entity_id",
        "course_sessions",
        ["snapshot_payor_legal_entity_id"],
        unique=False,
    )
    op.execute(
        """
        UPDATE course_sessions AS cs
        SET snapshot_payor_legal_entity_id = ct.payor_legal_entity_id
        FROM course_types AS ct
        WHERE cs.snapshot_payor_legal_entity_id IS NULL
          AND cs.course_type_id = ct.id
          AND ct.payor_legal_entity_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE course_sessions
        SET snapshot_payor_legal_entity_id = snapshot_seller_legal_entity_id
        WHERE snapshot_payor_legal_entity_id IS NULL
          AND snapshot_seller_legal_entity_id IS NOT NULL
        """
    )
    op.execute(
        """
        WITH fallback_entity AS (
            SELECT id
            FROM legal_entities
            ORDER BY is_active DESC, created_at ASC, id ASC
            LIMIT 1
        )
        UPDATE course_sessions
        SET snapshot_payor_legal_entity_id = (SELECT id FROM fallback_entity)
        WHERE snapshot_payor_legal_entity_id IS NULL
        """
    )
    op.alter_column("course_sessions", "snapshot_payor_legal_entity_id", nullable=False)

    op.create_table(
        "teacher_monthly_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payor_legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("attendance_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("totals_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dispute_message_last", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("month >= 1 AND month <= 12", name="ck_teacher_monthly_statements_month_range"),
        sa.ForeignKeyConstraint(["payor_legal_entity_id"], ["legal_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["teacher_id"], ["professors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "teacher_id",
            "payor_legal_entity_id",
            "year",
            "month",
            name="uq_teacher_monthly_statements_teacher_payor_year_month",
        ),
    )
    op.create_index(
        "ix_teacher_monthly_statements_teacher_period",
        "teacher_monthly_statements",
        ["teacher_id", "year", "month"],
        unique=False,
    )

    op.create_table(
        "teacher_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payor_legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=120), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("is_vat_applicable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("totals_ht", sa.Numeric(12, 2), nullable=False),
        sa.Column("totals_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("totals_ttc", sa.Numeric(12, 2), nullable=False),
        sa.Column("recipient_company_name", sa.Text(), nullable=False),
        sa.Column("recipient_company_address", sa.Text(), nullable=False),
        sa.Column("recipient_company_siret", sa.Text(), nullable=True),
        sa.Column("recipient_company_vat", sa.Text(), nullable=True),
        sa.Column("teacher_siret_display", sa.Text(), nullable=False),
        sa.Column("teacher_iban", sa.Text(), nullable=False),
        sa.Column("pdf_storage_key", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default=sa.text("'generated'")),
        sa.Column("sent_to_accounting_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["payor_legal_entity_id"], ["legal_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["statement_id"], ["teacher_monthly_statements.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["teacher_id"], ["professors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number"),
    )
    op.create_index("ix_teacher_invoices_teacher_id", "teacher_invoices", ["teacher_id"], unique=False)
    op.create_index("ix_teacher_invoices_statement_id", "teacher_invoices", ["statement_id"], unique=False)
    op.create_index(
        "ix_teacher_invoices_teacher_invoice_date",
        "teacher_invoices",
        ["teacher_id", "invoice_date"],
        unique=False,
    )

    op.create_table(
        "teacher_invoice_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("course_type_label", sa.Text(), nullable=False),
        sa.Column("hours", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_rate_ht", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount_ht", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount_ttc", sa.Numeric(12, 2), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["course_type_id"], ["course_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["teacher_invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_teacher_invoice_lines_invoice_id", "teacher_invoice_lines", ["invoice_id"], unique=False)

    op.create_table(
        "teacher_statement_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["statement_id"], ["teacher_monthly_statements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["professors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teacher_statement_messages_statement_id",
        "teacher_statement_messages",
        ["statement_id"],
        unique=False,
    )

    op.create_table(
        "teacher_invoice_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["teacher_invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["statement_id"], ["teacher_monthly_statements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["teacher_id"], ["professors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teacher_invoice_audit_events_lookup",
        "teacher_invoice_audit_events",
        ["teacher_id", "statement_id", "invoice_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "document_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("html_template", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.execute(
        """
        INSERT INTO document_templates (key, html_template, version, updated_at)
        SELECT
            'teacher_invoice',
            '<h1>Facture professeur</h1><p>Numero: {{invoice_number_display}}</p><p>Periode: {{invoice_period_label}}</p><p>Total TTC: {{totals_ttc}}</p>',
            1,
            now()
        WHERE NOT EXISTS (
            SELECT 1 FROM document_templates WHERE key = 'teacher_invoice'
        )
        """
    )


def downgrade() -> None:
    op.drop_table("document_templates")

    op.drop_index("ix_teacher_invoice_audit_events_lookup", table_name="teacher_invoice_audit_events")
    op.drop_table("teacher_invoice_audit_events")

    op.drop_index("ix_teacher_statement_messages_statement_id", table_name="teacher_statement_messages")
    op.drop_table("teacher_statement_messages")

    op.drop_index("ix_teacher_invoice_lines_invoice_id", table_name="teacher_invoice_lines")
    op.drop_table("teacher_invoice_lines")

    op.drop_index("ix_teacher_invoices_teacher_invoice_date", table_name="teacher_invoices")
    op.drop_index("ix_teacher_invoices_statement_id", table_name="teacher_invoices")
    op.drop_index("ix_teacher_invoices_teacher_id", table_name="teacher_invoices")
    op.drop_table("teacher_invoices")

    op.drop_index("ix_teacher_monthly_statements_teacher_period", table_name="teacher_monthly_statements")
    op.drop_table("teacher_monthly_statements")

    op.drop_index("ix_course_sessions_snapshot_payor_legal_entity_id", table_name="course_sessions")
    op.drop_constraint("fk_course_sessions_snapshot_payor_legal_entity_id", "course_sessions", type_="foreignkey")
    op.drop_column("course_sessions", "snapshot_payor_legal_entity_id")

    op.drop_index("ix_course_types_payor_legal_entity_id", table_name="course_types")
    op.drop_constraint("fk_course_types_payor_legal_entity_id", "course_types", type_="foreignkey")
    op.drop_column("course_types", "payor_legal_entity_id")

    op.drop_column("legal_entities", "accounting_email")

    op.drop_column("professors", "teacher_company_address")
    op.drop_column("professors", "teacher_company_name")
    op.drop_column("professors", "teacher_iban")
    op.drop_column("professors", "teacher_siret")
    op.drop_column("professors", "teacher_vat_rate")
    op.drop_column("professors", "teacher_is_vat_applicable")
    op.drop_column("professors", "teacher_invoice_counter")
