"""forfait formula dates and per-activity client pricing

Revision ID: 20260301_0043
Revises: 20260228_0042
Create Date: 2026-03-01 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260301_0043"
down_revision: Union[str, None] = "20260228_0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("forfait_start_date", sa.Date(), nullable=True))
    op.add_column("plans", sa.Column("forfait_end_date", sa.Date(), nullable=True))

    op.create_table(
        "client_forfait_activity_pricing",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loyalty_discount_per_hour_ttc", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("family_discount_per_hour_ttc", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("short_commitment_supplement_per_hour_ttc", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["subscription_id"], ["client_plan_subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_type_id"], ["course_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "course_type_id", name="uq_client_forfait_activity_pricing"),
    )
    op.create_check_constraint(
        "ck_cfap_loyalty_nn",
        "client_forfait_activity_pricing",
        "loyalty_discount_per_hour_ttc >= 0",
    )
    op.create_check_constraint(
        "ck_cfap_family_nn",
        "client_forfait_activity_pricing",
        "family_discount_per_hour_ttc >= 0",
    )
    op.create_check_constraint(
        "ck_cfap_short_commit_nn",
        "client_forfait_activity_pricing",
        "short_commitment_supplement_per_hour_ttc >= 0",
    )

    op.alter_column("client_forfait_activity_pricing", "loyalty_discount_per_hour_ttc", server_default=None)
    op.alter_column("client_forfait_activity_pricing", "family_discount_per_hour_ttc", server_default=None)
    op.alter_column("client_forfait_activity_pricing", "short_commitment_supplement_per_hour_ttc", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_cfap_short_commit_nn", "client_forfait_activity_pricing", type_="check")
    op.drop_constraint("ck_cfap_family_nn", "client_forfait_activity_pricing", type_="check")
    op.drop_constraint("ck_cfap_loyalty_nn", "client_forfait_activity_pricing", type_="check")
    op.drop_table("client_forfait_activity_pricing")

    op.drop_column("plans", "forfait_end_date")
    op.drop_column("plans", "forfait_start_date")
