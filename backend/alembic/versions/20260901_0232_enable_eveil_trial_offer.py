"""Enable the explicit trial offer for Eveil musical."""

from alembic import op


revision = "20260901_0232"
down_revision = "20260831_0231"
branch_labels = None
depends_on = None


TRIAL_PLAN_CODE = "FORM_COURS_D_ESSAI_DE_PIANO_EN_PR_SENTIEL_D791C0"
EVEIL_COURSE_TYPE_CODE = "ACT_EVEIL_MUSICAL_98E099"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO plan_entitlements (plan_id, course_type_id)
        SELECT plan.id, course_type.id
        FROM plans AS plan
        JOIN course_types AS course_type
          ON course_type.code = '{EVEIL_COURSE_TYPE_CODE}'
        WHERE plan.code = '{TRIAL_PLAN_CODE}'
          AND plan.is_trial_offer = true
        ON CONFLICT (plan_id, course_type_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM plan_entitlements AS entitlement
        USING plans AS plan, course_types AS course_type
        WHERE entitlement.plan_id = plan.id
          AND entitlement.course_type_id = course_type.id
          AND plan.code = '{TRIAL_PLAN_CODE}'
          AND course_type.code = '{EVEIL_COURSE_TYPE_CODE}'
        """
    )
