"""add parent prospect relation and adult-only unique email

Revision ID: 20260313_0071
Revises: 20260313_0070
Create Date: 2026-03-13 14:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260313_0071"
down_revision: Union[str, None] = "20260313_0070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prospects", sa.Column("parent_prospect_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_prospects_parent_prospect_id_prospects",
        "prospects",
        "prospects",
        ["parent_prospect_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_prospects_parent_prospect_id", "prospects", ["parent_prospect_id"])

    op.drop_constraint("uq_prospects_email", "prospects", type_="unique")
    op.create_index(
        "uq_prospects_email_adult",
        "prospects",
        ["email"],
        unique=True,
        postgresql_where=sa.text("coalesce(meta->>'prospect_type','adult') <> 'child'"),
    )


def downgrade() -> None:
    op.drop_index("uq_prospects_email_adult", table_name="prospects")
    op.create_unique_constraint("uq_prospects_email", "prospects", ["email"])

    op.drop_index("ix_prospects_parent_prospect_id", table_name="prospects")
    op.drop_constraint("fk_prospects_parent_prospect_id_prospects", "prospects", type_="foreignkey")
    op.drop_column("prospects", "parent_prospect_id")
