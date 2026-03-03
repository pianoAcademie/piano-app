"""professor salary payments

Revision ID: 20260305_0050
Revises: 20260305_0049
Create Date: 2026-03-05 10:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260305_0050"
down_revision: Union[str, None] = "20260305_0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    salary_payment_method = postgresql.ENUM(
        "BANK_TRANSFER",
        "CHEQUE",
        "CASH",
        name="salary_payment_method",
    )
    salary_payment_method.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "professor_salary_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("invoice_number", sa.String(length=120), nullable=False),
        sa.Column(
            "payment_method",
            postgresql.ENUM(
                "BANK_TRANSFER",
                "CHEQUE",
                "CASH",
                name="salary_payment_method",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'BANK_TRANSFER'::salary_payment_method"),
        ),
        sa.Column("amount_excl_vat", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("amount_incl_vat", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("settled_payout_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("amount_excl_vat >= 0", name="ck_prof_salary_payments_amount_excl_non_negative"),
        sa.CheckConstraint("amount_incl_vat >= 0", name="ck_prof_salary_payments_amount_incl_non_negative"),
        sa.CheckConstraint("amount_incl_vat >= amount_excl_vat", name="ck_prof_salary_payments_ttc_gte_ht"),
        sa.ForeignKeyConstraint(["professor_id"], ["professors.id"], name="fk_prof_salary_payments_professor", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_prof_salary_payments_actor", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prof_salary_payments_professor", "professor_salary_payments", ["professor_id"])
    op.create_index("ix_prof_salary_payments_reference_date", "professor_salary_payments", ["reference_date"])
    op.create_index("ix_prof_salary_payments_payment_date", "professor_salary_payments", ["payment_date"])


def downgrade() -> None:
    op.drop_index("ix_prof_salary_payments_payment_date", table_name="professor_salary_payments")
    op.drop_index("ix_prof_salary_payments_reference_date", table_name="professor_salary_payments")
    op.drop_index("ix_prof_salary_payments_professor", table_name="professor_salary_payments")
    op.drop_table("professor_salary_payments")

    salary_payment_method = postgresql.ENUM(
        "BANK_TRANSFER",
        "CHEQUE",
        "CASH",
        name="salary_payment_method",
    )
    salary_payment_method.drop(op.get_bind(), checkfirst=True)
