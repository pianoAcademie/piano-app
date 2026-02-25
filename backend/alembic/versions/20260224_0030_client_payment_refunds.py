"""add client payment refunds

Revision ID: 20260224_0030
Revises: 20260224_0029
Create Date: 2026-02-24 21:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260224_0030"
down_revision: Union[str, None] = "20260224_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_payment_refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_incl_vat", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_client_payment_refunds_user_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_client_payment_refunds_actor_user_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source", "source_payment_id", name="uq_client_payment_refund_source"),
    )
    op.create_index("ix_client_payment_refunds_user_id", "client_payment_refunds", ["user_id"], unique=False)
    op.create_index(
        "ix_client_payment_refunds_source_payment_id",
        "client_payment_refunds",
        ["source", "source_payment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_client_payment_refunds_source_payment_id", table_name="client_payment_refunds")
    op.drop_index("ix_client_payment_refunds_user_id", table_name="client_payment_refunds")
    op.drop_table("client_payment_refunds")
