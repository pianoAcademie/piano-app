"""activity-level reminder overrides for email and sms

Revision ID: 20260305_0048
Revises: 20260305_0047
Create Date: 2026-03-05 00:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260305_0048"
down_revision: Union[str, None] = "20260305_0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_types", sa.Column("email_reminder_hours_before_start", sa.Integer(), nullable=True))
    op.add_column("course_types", sa.Column("sms_reminder_hours_before_start", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_course_types_email_reminder_hours_non_negative",
        "course_types",
        "email_reminder_hours_before_start IS NULL OR email_reminder_hours_before_start >= 0",
    )
    op.create_check_constraint(
        "ck_course_types_sms_reminder_hours_non_negative",
        "course_types",
        "sms_reminder_hours_before_start IS NULL OR sms_reminder_hours_before_start >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_course_types_sms_reminder_hours_non_negative", "course_types", type_="check")
    op.drop_constraint("ck_course_types_email_reminder_hours_non_negative", "course_types", type_="check")
    op.drop_column("course_types", "sms_reminder_hours_before_start")
    op.drop_column("course_types", "email_reminder_hours_before_start")
