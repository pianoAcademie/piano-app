"""Add pricing, VAT and booking snapshots

Revision ID: 20260211_0005
Revises: 20260211_0004
Create Date: 2026-02-11 16:05:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260211_0005"
down_revision: Union[str, None] = "20260211_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("residence_country", sa.String(length=2), nullable=False, server_default=sa.text("'FR'")))
    op.add_column("users", sa.Column("preferred_currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")))

    op.create_table(
        "vat_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("service_code", sa.String(length=80), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_vat_rules_lookup",
        "vat_rules",
        ["country_code", "service_code", "valid_from"],
        unique=False,
    )

    op.create_table(
        "plan_prices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("residence_country", sa.String(length=2), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("price_excl_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("plan_id", "residence_country", "currency_code", "valid_from", name="uq_plan_prices"),
    )
    op.create_index(
        "idx_plan_prices_lookup",
        "plan_prices",
        ["plan_id", "residence_country", "currency_code", "valid_from"],
        unique=False,
    )

    op.create_table(
        "course_type_prices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "course_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("residence_country", sa.String(length=2), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("price_excl_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "course_type_id",
            "residence_country",
            "currency_code",
            "valid_from",
            name="uq_course_type_prices",
        ),
    )
    op.create_index(
        "idx_course_type_prices_lookup",
        "course_type_prices",
        ["course_type_id", "residence_country", "currency_code", "valid_from"],
        unique=False,
    )

    op.add_column(
        "bookings",
        sa.Column("price_excl_vat_snapshot", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "bookings",
        sa.Column("vat_rate_snapshot", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "bookings",
        sa.Column("vat_amount_snapshot", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "bookings",
        sa.Column("total_incl_vat_snapshot", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "bookings",
        sa.Column("currency_snapshot", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
    )

    op.execute(
        """
        INSERT INTO vat_rules (country_code, service_code, vat_rate, valid_from)
        VALUES
            ('FR', 'PIANO_CLASS', 20.00, '2020-01-01'),
            ('FR', 'SOLFEGE', 20.00, '2020-01-01'),
            ('FR', 'STUDIO', 20.00, '2020-01-01'),
            ('FR', 'COURSE_PACKAGE', 20.00, '2020-01-01'),
            ('FR', 'SUBSCRIPTION', 20.00, '2020-01-01'),
            ('US', 'PIANO_CLASS', 0.00, '2020-01-01'),
            ('US', 'SOLFEGE', 0.00, '2020-01-01'),
            ('US', 'STUDIO', 0.00, '2020-01-01'),
            ('US', 'COURSE_PACKAGE', 0.00, '2020-01-01'),
            ('US', 'SUBSCRIPTION', 0.00, '2020-01-01')
        """
    )

    op.execute(
        """
        INSERT INTO plan_prices (plan_id, residence_country, currency_code, price_excl_vat, valid_from)
        SELECT id, NULL, 'EUR',
            CASE code
                WHEN 'PACK_5_PIANO' THEN 250.00
                WHEN 'PACK_10_MULTI' THEN 450.00
                WHEN 'SUB_MONTHLY_ONLINE' THEN 120.00
                ELSE 0.00
            END,
            '2020-01-01'
        FROM plans
        """
    )

    op.execute(
        """
        INSERT INTO plan_prices (plan_id, residence_country, currency_code, price_excl_vat, valid_from)
        SELECT id, 'US', 'USD',
            CASE code
                WHEN 'PACK_5_PIANO' THEN 280.00
                WHEN 'PACK_10_MULTI' THEN 500.00
                WHEN 'SUB_MONTHLY_ONLINE' THEN 135.00
                ELSE 0.00
            END,
            '2020-01-01'
        FROM plans
        """
    )

    op.execute(
        """
        INSERT INTO course_type_prices (course_type_id, residence_country, currency_code, price_excl_vat, valid_from)
        SELECT id, NULL, 'EUR',
            CASE code
                WHEN 'PIANO_GROUP_ONSITE_1H' THEN 50.00
                WHEN 'PIANO_GROUP_ONLINE_1H' THEN 45.00
                WHEN 'SOLFEGE_ONLINE_30M' THEN 30.00
                WHEN 'STUDIO_REHEARSAL' THEN 40.00
                ELSE 0.00
            END,
            '2020-01-01'
        FROM course_types
        """
    )

    op.execute(
        """
        INSERT INTO course_type_prices (course_type_id, residence_country, currency_code, price_excl_vat, valid_from)
        SELECT id, 'US', 'USD',
            CASE code
                WHEN 'PIANO_GROUP_ONSITE_1H' THEN 56.00
                WHEN 'PIANO_GROUP_ONLINE_1H' THEN 50.00
                WHEN 'SOLFEGE_ONLINE_30M' THEN 34.00
                WHEN 'STUDIO_REHEARSAL' THEN 44.00
                ELSE 0.00
            END,
            '2020-01-01'
        FROM course_types
        """
    )


def downgrade() -> None:
    op.drop_column("bookings", "currency_snapshot")
    op.drop_column("bookings", "total_incl_vat_snapshot")
    op.drop_column("bookings", "vat_amount_snapshot")
    op.drop_column("bookings", "vat_rate_snapshot")
    op.drop_column("bookings", "price_excl_vat_snapshot")

    op.drop_index("idx_course_type_prices_lookup", table_name="course_type_prices")
    op.drop_table("course_type_prices")

    op.drop_index("idx_plan_prices_lookup", table_name="plan_prices")
    op.drop_table("plan_prices")

    op.drop_index("idx_vat_rules_lookup", table_name="vat_rules")
    op.drop_table("vat_rules")

    op.drop_column("users", "preferred_currency")
    op.drop_column("users", "residence_country")
