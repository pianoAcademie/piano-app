"""add client notes and manual credit balances

Revision ID: 20260224_0029
Revises: 20260224_0028
Create Date: 2026-02-24 20:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260224_0029"
down_revision: Union[str, None] = "20260224_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_manual_credit_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credit_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credits_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_client_manual_credit_balances_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["credit_type_id"],
            ["credit_types.id"],
            name="fk_client_manual_credit_balances_credit_type_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "credit_type_id", name="uq_client_manual_credit_balance_user_credit_type"),
    )
    op.create_index("ix_client_manual_credit_balances_user_id", "client_manual_credit_balances", ["user_id"], unique=False)

    op.create_table(
        "client_note_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_type", sa.String(length=20), nullable=False, server_default=sa.text("'AUTO'")),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_client_note_entries_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], name="fk_client_note_entries_author_user_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_client_note_entries_user_id", "client_note_entries", ["user_id"], unique=False)
    op.create_index("ix_client_note_entries_created_at", "client_note_entries", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_client_note_entries_created_at", table_name="client_note_entries")
    op.drop_index("ix_client_note_entries_user_id", table_name="client_note_entries")
    op.drop_table("client_note_entries")

    op.drop_index("ix_client_manual_credit_balances_user_id", table_name="client_manual_credit_balances")
    op.drop_table("client_manual_credit_balances")
