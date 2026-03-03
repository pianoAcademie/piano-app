"""add activity billing entity, session snapshot, and invoice lines

Revision ID: 20260306_0052
Revises: 20260305_0051
Create Date: 2026-03-06 09:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260306_0052"
down_revision: Union[str, None] = "20260305_0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_types",
        sa.Column(
            "billing_entity_code",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'PIANO_ACADEMIE'"),
        ),
    )

    op.add_column(
        "course_sessions",
        sa.Column(
            "billing_entity_snapshot",
            sa.String(length=40),
            nullable=True,
            server_default=sa.text("'PIANO_ACADEMIE'"),
        ),
    )
    op.execute(
        """
        UPDATE course_sessions AS cs
        SET billing_entity_snapshot = COALESCE(ct.billing_entity_code, 'PIANO_ACADEMIE')
        FROM course_types AS ct
        WHERE ct.id = cs.course_type_id
          AND cs.billing_entity_snapshot IS NULL
        """
    )
    op.execute("UPDATE course_sessions SET billing_entity_snapshot = 'PIANO_ACADEMIE' WHERE billing_entity_snapshot IS NULL")
    op.alter_column("course_sessions", "billing_entity_snapshot", nullable=False)

    op.create_table(
        "client_invoice_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("amount_excl_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(6, 3), nullable=False),
        sa.Column("vat_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_incl_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "billing_entity",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'PIANO_ACADEMIE'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["note_id"], ["client_note_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_id", "source", "source_payment_id", name="uq_client_invoice_line_note_source_payment"),
    )
    op.create_index("ix_client_invoice_lines_note_id", "client_invoice_lines", ["note_id"], unique=False)
    op.create_index("ix_client_invoice_lines_user_id", "client_invoice_lines", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_client_invoice_lines_user_id", table_name="client_invoice_lines")
    op.drop_index("ix_client_invoice_lines_note_id", table_name="client_invoice_lines")
    op.drop_table("client_invoice_lines")

    op.drop_column("course_sessions", "billing_entity_snapshot")
    op.drop_column("course_types", "billing_entity_code")
