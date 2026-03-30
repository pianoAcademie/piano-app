"""add payment receipts for deferred future-service invoicing

Revision ID: 20260330_0092
Revises: 20260330_0091
Create Date: 2026-03-30 20:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260330_0092"
down_revision: Union[str, None] = "20260330_0091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("receipt_number", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("final_invoice_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("manual_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'EUR'"), nullable=False),
        sa.Column("amount_paid", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_method", sa.String(length=40), nullable=True),
        sa.Column("payment_provider", sa.String(length=40), nullable=True),
        sa.Column("payment_transaction_reference", sa.String(length=255), nullable=True),
        sa.Column("reservation_label", sa.String(length=255), nullable=False),
        sa.Column("scheduled_service_date", sa.Date(), nullable=True),
        sa.Column("location_label", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_path", sa.String(length=500), nullable=True),
        sa.Column("final_invoice_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["final_invoice_note_id"], ["client_note_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["manual_transaction_id"], ["client_manual_transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_number", name="uq_payment_receipts_receipt_number"),
    )
    op.create_index("ix_payment_receipts_booking_id", "payment_receipts", ["booking_id"])
    op.create_index("ix_payment_receipts_customer_id", "payment_receipts", ["customer_id"])
    op.create_index("ix_payment_receipts_final_invoice_note_id", "payment_receipts", ["final_invoice_note_id"])
    op.create_index(
        "ix_payment_receipts_provider_reference",
        "payment_receipts",
        ["payment_transaction_reference"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_receipts_provider_reference", table_name="payment_receipts")
    op.drop_index("ix_payment_receipts_final_invoice_note_id", table_name="payment_receipts")
    op.drop_index("ix_payment_receipts_customer_id", table_name="payment_receipts")
    op.drop_index("ix_payment_receipts_booking_id", table_name="payment_receipts")
    op.drop_table("payment_receipts")
