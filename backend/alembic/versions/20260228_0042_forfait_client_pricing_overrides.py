"""add client-level forfait pricing overrides

Revision ID: 20260228_0042
Revises: 20260227_0041
Create Date: 2026-02-28 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260228_0042"
down_revision: Union[str, None] = "20260227_0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "client_plan_subscriptions",
        sa.Column(
            "forfait_loyalty_discount_per_hour_ttc",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "client_plan_subscriptions",
        sa.Column(
            "forfait_family_discount_per_hour_ttc",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "client_plan_subscriptions",
        sa.Column(
            "forfait_short_commitment_supplement_per_hour_ttc",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_check_constraint(
        "ck_client_plan_subscriptions_forfait_loyalty_non_negative",
        "client_plan_subscriptions",
        "forfait_loyalty_discount_per_hour_ttc >= 0",
    )
    op.create_check_constraint(
        "ck_client_plan_subscriptions_forfait_family_non_negative",
        "client_plan_subscriptions",
        "forfait_family_discount_per_hour_ttc >= 0",
    )
    op.create_check_constraint(
        "ck_client_plan_subscriptions_forfait_short_commitment_non_negative",
        "client_plan_subscriptions",
        "forfait_short_commitment_supplement_per_hour_ttc >= 0",
    )

    op.alter_column("client_plan_subscriptions", "forfait_loyalty_discount_per_hour_ttc", server_default=None)
    op.alter_column("client_plan_subscriptions", "forfait_family_discount_per_hour_ttc", server_default=None)
    op.alter_column("client_plan_subscriptions", "forfait_short_commitment_supplement_per_hour_ttc", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_client_plan_subscriptions_forfait_short_commitment_non_negative",
        "client_plan_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_client_plan_subscriptions_forfait_family_non_negative",
        "client_plan_subscriptions",
        type_="check",
    )
    op.drop_constraint(
        "ck_client_plan_subscriptions_forfait_loyalty_non_negative",
        "client_plan_subscriptions",
        type_="check",
    )

    op.drop_column("client_plan_subscriptions", "forfait_short_commitment_supplement_per_hour_ttc")
    op.drop_column("client_plan_subscriptions", "forfait_family_discount_per_hour_ttc")
    op.drop_column("client_plan_subscriptions", "forfait_loyalty_discount_per_hour_ttc")
