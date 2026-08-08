"""Add per-activity trial authorization and pricing.

Revision ID: 20260808_0188
Revises: 20260808_0187
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_0188"
down_revision = "20260808_0187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_types",
        sa.Column("trial_course_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "course_types",
        sa.Column("trial_course_price_ttc", sa.Numeric(12, 2), nullable=True),
    )
    op.create_check_constraint(
        "ck_course_types_trial_price_non_negative",
        "course_types",
        "trial_course_price_ttc IS NULL OR trial_course_price_ttc >= 0",
    )
    op.create_check_constraint(
        "ck_course_types_trial_configuration_complete",
        "course_types",
        "NOT trial_course_enabled OR (allows_student_bookings AND trial_course_price_ttc IS NOT NULL)",
    )

    # Preserve the trial activities already exposed through an active explicit
    # trial formula. Each activity can be edited independently after migration.
    op.execute(
        """
        WITH existing_trial_prices AS (
          SELECT
            entitlement.course_type_id,
            min(coalesce(plan.monthly_price_value, plan.monthly_price_excl_vat)) AS trial_price
          FROM plan_entitlements AS entitlement
          JOIN plans AS plan ON plan.id = entitlement.plan_id
          WHERE plan.is_trial_offer = true
            AND plan.active = true
            AND coalesce(plan.monthly_price_value, plan.monthly_price_excl_vat) IS NOT NULL
          GROUP BY entitlement.course_type_id
        )
        UPDATE course_types AS course_type
        SET
          trial_course_enabled = true,
          trial_course_price_ttc = existing_trial_prices.trial_price
        FROM existing_trial_prices
        WHERE course_type.id = existing_trial_prices.course_type_id
          AND course_type.allows_student_bookings = true
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_course_types_trial_configuration_complete", "course_types", type_="check")
    op.drop_constraint("ck_course_types_trial_price_non_negative", "course_types", type_="check")
    op.drop_column("course_types", "trial_course_price_ttc")
    op.drop_column("course_types", "trial_course_enabled")
