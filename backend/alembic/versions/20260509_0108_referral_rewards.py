"""add referral rewards

Revision ID: 20260509_0108
Revises: 20260507_0107
Create Date: 2026-05-09 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260509_0108"
down_revision: Union[str, None] = "20260507_0107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_rewards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("typeform_intake_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("referred_client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("referred_student_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("referrer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("declared_referrer_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default=sa.text("'DECLARED'")),
        sa.Column("match_status", sa.String(length=40), nullable=False, server_default=sa.text("'UNMATCHED'")),
        sa.Column("match_confidence", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("match_candidates_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reward_amount", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("trigger_ratio", sa.Numeric(6, 4), nullable=False, server_default=sa.text("0.5000")),
        sa.Column("trigger_invoice_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("credit_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("announcement_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credit_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credit_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["credit_transaction_id"], ["client_manual_transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referred_client_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referred_student_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trigger_invoice_note_id"], ["client_note_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["typeform_intake_id"], ["typeform_intakes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credit_transaction_id", name="uq_referral_rewards_credit_transaction"),
        sa.UniqueConstraint("quote_id", name="uq_referral_rewards_quote"),
        sa.UniqueConstraint("typeform_intake_id", name="uq_referral_rewards_typeform_intake"),
    )
    op.create_index("ix_referral_rewards_invoice_note_id", "referral_rewards", ["trigger_invoice_note_id"], unique=False)
    op.create_index("ix_referral_rewards_referred_client_id", "referral_rewards", ["referred_client_id"], unique=False)
    op.create_index("ix_referral_rewards_referrer_user_id", "referral_rewards", ["referrer_user_id"], unique=False)
    op.create_index("ix_referral_rewards_status", "referral_rewards", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_referral_rewards_status", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_referrer_user_id", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_referred_client_id", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_invoice_note_id", table_name="referral_rewards")
    op.drop_table("referral_rewards")
