"""add client manual transactions

Revision ID: 20260227_0039
Revises: 20260227_0038
Create Date: 2026-02-27 13:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260227_0039"
down_revision: Union[str, None] = "20260227_0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_manual_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'COMPLETED'")),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("amount_excl_vat", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(precision=6, scale=3), nullable=False, server_default=sa.text("0")),
        sa.Column("vat_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_incl_vat", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "transaction_type IN ('PAYMENT', 'REFUND', 'CHARGE', 'DISCOUNT')",
            name="ck_client_manual_transactions_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_client_manual_transactions_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["student_user_id"],
            ["users.id"],
            name="fk_client_manual_transactions_student_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_client_manual_transactions_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_client_manual_transactions_user_id", "client_manual_transactions", ["user_id"], unique=False)
    op.create_index("ix_client_manual_transactions_occurred_at", "client_manual_transactions", ["occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_client_manual_transactions_occurred_at", table_name="client_manual_transactions")
    op.drop_index("ix_client_manual_transactions_user_id", table_name="client_manual_transactions")
    op.drop_table("client_manual_transactions")
