"""add generated reports

Revision ID: 20260518_0123
Revises: 20260517_0122
Create Date: 2026-05-18 11:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260518_0123"
down_revision: Union[str, None] = "20260517_0122"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_type", sa.String(length=80), nullable=False),
        sa.Column("report_label", sa.Text(), nullable=False),
        sa.Column("file_format", sa.String(length=20), nullable=False, server_default=sa.text("'PDF'")),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("criteria_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generated_reports_created_at", "generated_reports", ["created_at"], unique=False)
    op.create_index("ix_generated_reports_report_type", "generated_reports", ["report_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_generated_reports_report_type", table_name="generated_reports")
    op.drop_index("ix_generated_reports_created_at", table_name="generated_reports")
    op.drop_table("generated_reports")
