"""configure the migrated monthly onsite plan entitlements

Revision ID: 20260805_0177
Revises: 20260805_0176
Create Date: 2026-08-05
"""

from __future__ import annotations

from alembic import op


revision = "20260805_0177"
down_revision = "20260805_0176"
branch_labels = None
depends_on = None


PLAN_CODE = "FORM_ABONNEMENT_MENSUEL_PRESENTIEL_STUDIO_SOL_E2ED74"
INCLUDED_CREDIT_TYPE_CODES = (
    "CREDIT_PIANO_ONSITE",
    "CREDIT_STUDIO",
    "CREDIT_SOLFEGE_ONLINE",
    "CREDIT_SOLFEGE_ONSITE",
)


def upgrade() -> None:
    credit_type_codes = ", ".join(f"'{code}'" for code in INCLUDED_CREDIT_TYPE_CODES)
    op.execute(
        f"""
        INSERT INTO plan_entitlements (plan_id, course_type_id)
        SELECT p.id, course_type.id
        FROM plans p
        JOIN course_types course_type ON true
        JOIN credit_types credit_type ON credit_type.id = course_type.credit_type_id
        WHERE p.code = '{PLAN_CODE}'
          AND credit_type.code IN ({credit_type_codes})
        ON CONFLICT (plan_id, course_type_id) DO NOTHING
        """
    )


def downgrade() -> None:
    credit_type_codes = ", ".join(f"'{code}'" for code in INCLUDED_CREDIT_TYPE_CODES)
    op.execute(
        f"""
        DELETE FROM plan_entitlements entitlement
        USING plans p, course_types course_type, credit_types credit_type
        WHERE entitlement.plan_id = p.id
          AND entitlement.course_type_id = course_type.id
          AND course_type.credit_type_id = credit_type.id
          AND p.code = '{PLAN_CODE}'
          AND credit_type.code IN ({credit_type_codes})
        """
    )
