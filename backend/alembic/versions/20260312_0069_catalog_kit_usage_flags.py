"""add usage flags to catalog kits

Revision ID: 20260312_0069
Revises: 20260312_0068
Create Date: 2026-03-12 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260312_0069"
down_revision = "20260312_0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_kits",
        sa.Column("use_in_manual_billing", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "catalog_kits",
        sa.Column("use_in_enrollments", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("catalog_kits", "use_in_enrollments")
    op.drop_column("catalog_kits", "use_in_manual_billing")
