"""add formula and school year defaults on quote types

Revision ID: 20260314_0077
Revises: 20260314_0076
Create Date: 2026-03-14 23:55:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260314_0077"
down_revision: Union[str, None] = "20260314_0076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quote_types",
        sa.Column("formula_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "quote_types",
        sa.Column("school_year_label", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_quote_types_formula_id", "quote_types", ["formula_id"], unique=False)
    op.create_foreign_key(
        "fk_quote_types_formula_id_plans",
        "quote_types",
        "plans",
        ["formula_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_quote_types_formula_id_plans", "quote_types", type_="foreignkey")
    op.drop_index("ix_quote_types_formula_id", table_name="quote_types")
    op.drop_column("quote_types", "school_year_label")
    op.drop_column("quote_types", "formula_id")
