"""Add professor selectable flag on product categories

Revision ID: 20260310_0062
Revises: 20260309_0061
Create Date: 2026-03-10 09:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260310_0062"
down_revision: Union[str, None] = "20260309_0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_categories",
        sa.Column(
            "can_be_requested_by_professor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.execute(
        """
        UPDATE product_categories
        SET can_be_requested_by_professor = false
        WHERE lower(name) IN ('gestion', 'cours')
        """
    )


def downgrade() -> None:
    op.drop_column("product_categories", "can_be_requested_by_professor")
