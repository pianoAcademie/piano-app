"""Add bank transfer payment orders.

Revision ID: 20260525_0135
Revises: 20260525_0134
Create Date: 2026-05-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260525_0135"
down_revision = "20260525_0134"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bank_transfer_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_reference", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default=sa.text("'pending_bank_transfer'")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount_incl_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manual_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_note_id"], ["client_note_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_transaction_id"], ["client_manual_transactions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_reference", name="uq_bank_transfer_orders_reference"),
    )
    op.create_index("ix_bank_transfer_orders_invoice_note", "bank_transfer_orders", ["invoice_note_id"])
    op.create_index("ix_bank_transfer_orders_status_expires", "bank_transfer_orders", ["status", "expires_at"])

    op.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES
            ('bank_transfer_account_holder', 'SAS PIANO ACADEMIE', now()),
            ('bank_transfer_iban', 'FR76 1020 7000 9822 2117 9625 586', now()),
            ('bank_transfer_bic', 'CCBPFRPPMTG', now())
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_bank_transfer_orders_status_expires", table_name="bank_transfer_orders")
    op.drop_index("ix_bank_transfer_orders_invoice_note", table_name="bank_transfer_orders")
    op.drop_table("bank_transfer_orders")
