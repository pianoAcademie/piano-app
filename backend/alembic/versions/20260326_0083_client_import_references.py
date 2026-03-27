"""client import references

Revision ID: 20260326_0083
Revises: 20260325_0082
Create Date: 2026-03-26 10:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260326_0083"
down_revision: Union[str, None] = "20260325_0082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_import_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=40), nullable=False),
        sa.Column("external_kind", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("external_family_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system",
            "external_kind",
            "external_id",
            name="uq_client_import_references_source_kind_id",
        ),
    )
    op.create_index("ix_client_import_references_user_id", "client_import_references", ["user_id"], unique=False)
    op.create_index(
        "ix_client_import_references_family_id",
        "client_import_references",
        ["external_family_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_client_import_references_family_id", table_name="client_import_references")
    op.drop_index("ix_client_import_references_user_id", table_name="client_import_references")
    op.drop_table("client_import_references")
