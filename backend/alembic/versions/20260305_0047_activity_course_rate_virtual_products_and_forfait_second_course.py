"""activity course rate, virtual catalog products and forfait second-course discount

Revision ID: 20260305_0047
Revises: 20260304_0046
Create Date: 2026-03-05 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260305_0047"
down_revision: Union[str, None] = "20260304_0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_types", sa.Column("default_course_rate_ttc", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint(
        "ck_course_types_default_course_rate_non_negative",
        "course_types",
        "default_course_rate_ttc IS NULL OR default_course_rate_ttc >= 0",
    )

    op.add_column(
        "catalog_products",
        sa.Column("is_virtual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.add_column(
        "client_forfait_activity_pricing",
        sa.Column(
            "second_course_weekly_discount_per_hour_ttc",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "ck_cfap_second_weekly_nn",
        "client_forfait_activity_pricing",
        "second_course_weekly_discount_per_hour_ttc >= 0",
    )
    op.alter_column("client_forfait_activity_pricing", "second_course_weekly_discount_per_hour_ttc", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_cfap_second_weekly_nn", "client_forfait_activity_pricing", type_="check")
    op.drop_column("client_forfait_activity_pricing", "second_course_weekly_discount_per_hour_ttc")

    op.drop_column("catalog_products", "is_virtual")

    op.drop_constraint("ck_course_types_default_course_rate_non_negative", "course_types", type_="check")
    op.drop_column("course_types", "default_course_rate_ttc")
