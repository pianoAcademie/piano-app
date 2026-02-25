"""formula credit grants and tax mode pricing

Revision ID: 20260219_0023
Revises: 20260218_0022
Create Date: 2026-02-19 16:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260219_0023"
down_revision: Union[str, None] = "20260218_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'plan_price_tax_mode') THEN
                CREATE TYPE plan_price_tax_mode AS ENUM ('HT', 'TTC');
            END IF;
        END
        $$;
        """
    )

    op.add_column("plans", sa.Column("monthly_price_value", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column(
        "plans",
        sa.Column(
            "price_tax_mode",
            sa.Enum("HT", "TTC", name="plan_price_tax_mode", native_enum=True, create_type=False),
            nullable=True,
            server_default=sa.text("'HT'::plan_price_tax_mode"),
        ),
    )
    op.add_column("plans", sa.Column("signup_fee_value", sa.Numeric(precision=12, scale=2), nullable=True))

    op.execute(
        """
        UPDATE plans
        SET monthly_price_value = COALESCE(monthly_price_value, monthly_price_excl_vat),
            signup_fee_value = COALESCE(signup_fee_value, signup_fee_excl_vat),
            price_tax_mode = COALESCE(price_tax_mode, 'HT'::plan_price_tax_mode)
        """
    )

    op.alter_column("plans", "price_tax_mode", nullable=False, server_default=sa.text("'HT'::plan_price_tax_mode"))

    op.create_table(
        "plan_credit_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credit_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credits_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name="fk_plan_credit_grants_plan_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["credit_type_id"],
            ["credit_types.id"],
            name="fk_plan_credit_grants_credit_type_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "credit_type_id", name="uq_plan_credit_grants"),
    )
    op.create_index("ix_plan_credit_grants_plan_id", "plan_credit_grants", ["plan_id"], unique=False)

    # Backfill only plans with a single mapped credit type across entitlements.
    # Multi-credit plans remain on legacy credits_count fallback until manually edited.
    op.execute(
        """
        WITH plan_credit_scope AS (
            SELECT
                p.id AS plan_id,
                MIN(ct.credit_type_id::text)::uuid AS credit_type_id,
                COUNT(DISTINCT ct.credit_type_id) AS credit_type_count,
                MAX(p.credits_count) AS credits_count
            FROM plans p
            JOIN plan_entitlements pe ON pe.plan_id = p.id
            JOIN course_types ct ON ct.id = pe.course_type_id
            WHERE p.kind = 'PACK'::plan_kind
              AND p.credits_count IS NOT NULL
              AND p.credits_count > 0
              AND ct.credit_type_id IS NOT NULL
            GROUP BY p.id
        )
        INSERT INTO plan_credit_grants (plan_id, credit_type_id, credits_count)
        SELECT plan_id, credit_type_id, credits_count
        FROM plan_credit_scope
        WHERE credit_type_count = 1
        ON CONFLICT (plan_id, credit_type_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_plan_credit_grants_plan_id", table_name="plan_credit_grants")
    op.drop_table("plan_credit_grants")

    op.drop_column("plans", "signup_fee_value")
    op.drop_column("plans", "price_tax_mode")
    op.drop_column("plans", "monthly_price_value")

    op.execute("DROP TYPE IF EXISTS plan_price_tax_mode")
