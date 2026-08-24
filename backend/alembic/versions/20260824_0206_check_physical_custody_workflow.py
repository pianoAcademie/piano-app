"""Track check receipt location and physical custody.

Revision ID: 20260824_0206
Revises: 20260822_0205
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260824_0206"
down_revision = "20260822_0205"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_manual_transactions",
        sa.Column("check_receipt_location_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "client_manual_transactions",
        sa.Column("check_custody_status", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "client_manual_transactions",
        sa.Column("check_custody_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_client_manual_transactions_check_receipt_location",
        "client_manual_transactions",
        "locations",
        ["check_receipt_location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_client_manual_transactions_check_custody",
        "client_manual_transactions",
        ["check_custody_status"],
        unique=False,
    )
    # All checks already entered before this workflow are, by business rule,
    # physically in the hands of the administration.
    op.execute(
        sa.text(
            """
            UPDATE client_manual_transactions
            SET check_custody_status = CASE upper(status)
                    WHEN 'CHECK_DEPOSITED' THEN 'DEPOSITED_AT_BANK'
                    WHEN 'PAID' THEN 'CASHED'
                    WHEN 'CHECK_REFUSED' THEN 'REFUSED'
                    ELSE 'WITH_ADMINISTRATION'
                END,
                check_custody_updated_at = COALESCE(updated_at, created_at, now())
            WHERE transaction_type = 'PAYMENT'
              AND reference ILIKE 'MODE:CHECK%'
              AND check_custody_status IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_client_manual_transactions_check_custody", table_name="client_manual_transactions")
    op.drop_constraint(
        "fk_client_manual_transactions_check_receipt_location",
        "client_manual_transactions",
        type_="foreignkey",
    )
    op.drop_column("client_manual_transactions", "check_custody_updated_at")
    op.drop_column("client_manual_transactions", "check_custody_status")
    op.drop_column("client_manual_transactions", "check_receipt_location_id")
