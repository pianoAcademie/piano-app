"""add legal entity on quotes

Revision ID: 20260314_0078
Revises: 20260314_0077
Create Date: 2026-03-14 23:59:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260314_0078"
down_revision: Union[str, None] = "20260314_0077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_quotes_legal_entity_id", "quotes", ["legal_entity_id"], unique=False)
    op.create_foreign_key(
        "fk_quotes_legal_entity_id_legal_entities",
        "quotes",
        "legal_entities",
        ["legal_entity_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_quotes_legal_entity_id_legal_entities", "quotes", type_="foreignkey")
    op.drop_index("ix_quotes_legal_entity_id", table_name="quotes")
    op.drop_column("quotes", "legal_entity_id")
