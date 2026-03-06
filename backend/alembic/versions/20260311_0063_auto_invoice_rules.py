"""Add automatic invoice rules and occurrences

Revision ID: 20260311_0063
Revises: 20260310_0062
Create Date: 2026-03-11 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260311_0063"
down_revision: Union[str, None] = "20260310_0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_auto_invoice_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_start_date", sa.Date(), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("billing_timing", sa.String(length=30), nullable=False),
        sa.Column("due_date_rule_type", sa.String(length=30), nullable=False),
        sa.Column("due_date_days_offset", sa.Integer(), nullable=True),
        sa.Column("include_pending_lines", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("include_cancelled_lines", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("next_run_date", sa.Date(), nullable=False),
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("frequency IN ('MONTHLY','QUARTERLY','YEARLY')", name="ck_client_auto_invoice_rules_frequency"),
        sa.CheckConstraint(
            "billing_timing IN ('UPCOMING_LESSONS','PREVIOUS_LESSONS')",
            name="ck_client_auto_invoice_rules_billing_timing",
        ),
        sa.CheckConstraint(
            "due_date_rule_type IN ('SAME_DAY_ISSUE','X_DAYS_AFTER_ISSUE')",
            name="ck_client_auto_invoice_rules_due_date_rule_type",
        ),
        sa.CheckConstraint("due_date_days_offset IS NULL OR due_date_days_offset >= 0", name="ck_client_auto_invoice_rules_due_offset"),
        sa.CheckConstraint("status IN ('ACTIVE','PAUSED','ARCHIVED')", name="ck_client_auto_invoice_rules_status"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_client_auto_invoice_rules_status_next_run",
        "client_auto_invoice_rules",
        ["status", "next_run_date"],
        unique=False,
    )
    op.create_index(
        "ix_client_auto_invoice_rules_user_legal_entity",
        "client_auto_invoice_rules",
        ["user_id", "legal_entity_id"],
        unique=False,
    )

    op.create_table(
        "client_auto_invoice_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_key", sa.String(length=80), nullable=False),
        sa.Column("period_start_date", sa.Date(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'GENERATED'")),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('PROCESSING','GENERATED','SKIPPED_EMPTY','SKIPPED_DUPLICATE')",
            name="ck_client_auto_invoice_occurrences_status",
        ),
        sa.ForeignKeyConstraint(["note_id"], ["client_note_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rule_id"], ["client_auto_invoice_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "cycle_key", name="uq_client_auto_invoice_occurrence_rule_cycle"),
    )
    op.create_index(
        "ix_client_auto_invoice_occurrences_rule_generated",
        "client_auto_invoice_occurrences",
        ["rule_id", "generated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_client_auto_invoice_occurrences_rule_generated", table_name="client_auto_invoice_occurrences")
    op.drop_table("client_auto_invoice_occurrences")
    op.drop_index("ix_client_auto_invoice_rules_user_legal_entity", table_name="client_auto_invoice_rules")
    op.drop_index("ix_client_auto_invoice_rules_status_next_run", table_name="client_auto_invoice_rules")
    op.drop_table("client_auto_invoice_rules")
