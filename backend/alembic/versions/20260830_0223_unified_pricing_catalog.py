"""Extend the existing pricing catalog with channels and discount policies.

Revision ID: 20260830_0223
Revises: 20260830_0222
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260830_0223"
down_revision = "20260830_0222"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pricing_catalogs",
        sa.Column("lifecycle_status", sa.String(length=20), server_default=sa.text("'DRAFT'"), nullable=False),
    )
    op.add_column("pricing_catalogs", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_pricing_catalogs_lifecycle_status",
        "pricing_catalogs",
        "lifecycle_status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
    )
    # Existing active catalogs are already used by quotes. Mark them as
    # published without rewriting their prices or historical documents.
    op.execute(
        "UPDATE pricing_catalogs SET lifecycle_status = CASE WHEN is_active THEN 'PUBLISHED' ELSE 'ARCHIVED' END"
    )

    op.drop_constraint("uq_pricing_activity_prices_scope", "pricing_activity_prices", type_="unique")
    op.add_column(
        "pricing_activity_prices",
        sa.Column(
            "price_channel",
            sa.String(length=30),
            server_default=sa.text("'ANNUAL_FORFAIT'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_pricing_activity_prices_channel",
        "pricing_activity_prices",
        "price_channel IN ('STANDARD', 'ANNUAL_FORFAIT', 'TRIAL', 'EXTERNAL_UNIT')",
    )
    op.create_unique_constraint(
        "uq_pricing_activity_prices_scope",
        "pricing_activity_prices",
        ["catalog_id", "activity_id", "location_id", "student_category", "pricing_unit", "price_channel"],
    )

    op.add_column(
        "quote_discount_rules",
        sa.Column(
            "catalog_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pricing_catalogs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "quote_discount_rules",
        sa.Column("rule_kind", sa.String(length=30), server_default=sa.text("'CUSTOM'"), nullable=False),
    )
    op.add_column(
        "quote_discount_rules",
        sa.Column("calculation_mode", sa.String(length=30), server_default=sa.text("'PER_HOUR_TTC'"), nullable=False),
    )
    op.add_column(
        "quote_discount_rules",
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
    )
    op.add_column("quote_discount_rules", sa.Column("stacking_group", sa.String(length=60), nullable=True))
    op.add_column(
        "quote_discount_rules",
        sa.Column("is_stackable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "quote_discount_rules",
        sa.Column(
            "applies_to_channels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[\"ANNUAL_FORFAIT\"]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "quote_discount_rules",
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "quote_discount_rules",
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("quote_discount_rules", sa.Column("student_category", sa.String(length=80), nullable=True))
    op.create_check_constraint(
        "ck_quote_discount_rules_kind",
        "quote_discount_rules",
        "rule_kind IN ('LOYALTY', 'FAMILY', 'SECOND_COURSE', 'SHORT_COMMITMENT', 'CUSTOM')",
    )
    op.create_check_constraint(
        "ck_quote_discount_rules_calculation_mode",
        "quote_discount_rules",
        "calculation_mode IN ('PER_HOUR_TTC', 'PER_SESSION_TTC', 'PERCENT')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_quote_discount_rules_calculation_mode", "quote_discount_rules", type_="check")
    op.drop_constraint("ck_quote_discount_rules_kind", "quote_discount_rules", type_="check")
    op.drop_column("quote_discount_rules", "student_category")
    op.drop_column("quote_discount_rules", "location_id")
    op.drop_column("quote_discount_rules", "activity_id")
    op.drop_column("quote_discount_rules", "applies_to_channels")
    op.drop_column("quote_discount_rules", "is_stackable")
    op.drop_column("quote_discount_rules", "stacking_group")
    op.drop_column("quote_discount_rules", "priority")
    op.drop_column("quote_discount_rules", "calculation_mode")
    op.drop_column("quote_discount_rules", "rule_kind")
    op.drop_column("quote_discount_rules", "catalog_id")

    op.drop_constraint("uq_pricing_activity_prices_scope", "pricing_activity_prices", type_="unique")
    op.drop_constraint("ck_pricing_activity_prices_channel", "pricing_activity_prices", type_="check")
    op.drop_column("pricing_activity_prices", "price_channel")
    op.create_unique_constraint(
        "uq_pricing_activity_prices_scope",
        "pricing_activity_prices",
        ["catalog_id", "activity_id", "location_id", "student_category", "pricing_unit"],
    )

    op.drop_constraint("ck_pricing_catalogs_lifecycle_status", "pricing_catalogs", type_="check")
    op.drop_column("pricing_catalogs", "published_at")
    op.drop_column("pricing_catalogs", "lifecycle_status")
