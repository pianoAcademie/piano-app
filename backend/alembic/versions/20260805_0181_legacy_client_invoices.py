"""Store read-only historical client invoices.

Revision ID: 20260805_0181
Revises: 20260805_0180
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260805_0181"
down_revision = "20260805_0180"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_legacy_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False, server_default=sa.text("'SPORTIGO'")),
        sa.Column("source_customer_id", sa.String(length=80), nullable=True),
        sa.Column("external_reference", sa.String(length=120), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("total_incl_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("pdf_storage_key", sa.String(length=255), nullable=False),
        sa.Column("original_file_name", sa.String(length=255), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source", "external_reference", name="uq_client_legacy_invoice_source_reference"),
    )
    op.create_index(
        "ix_client_legacy_invoices_user_issued",
        "client_legacy_invoices",
        ["user_id", "issued_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_legacy_invoices_user_issued", table_name="client_legacy_invoices")
    op.drop_table("client_legacy_invoices")
