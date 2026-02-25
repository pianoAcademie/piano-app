"""Add configuration and formula fields on plans

Revision ID: 20260213_0012
Revises: 20260212_0011
Create Date: 2026-02-13 12:45:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260213_0012"
down_revision: Union[str, None] = "20260212_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("plans", sa.Column("signup_fee_excl_vat", sa.Numeric(12, 2), nullable=True))
    op.add_column("plans", sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column(
        "plans",
        sa.Column(
            "options_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "plans",
        sa.Column(
            "payment_methods_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "plans",
        sa.Column(
            "restrictions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("plans", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))


def downgrade() -> None:
    op.drop_column("plans", "updated_at")
    op.drop_column("plans", "restrictions_json")
    op.drop_column("plans", "payment_methods_json")
    op.drop_column("plans", "options_json")
    op.drop_column("plans", "is_private")
    op.drop_column("plans", "signup_fee_excl_vat")
    op.drop_column("plans", "description")
