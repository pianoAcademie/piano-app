"""Disable lesson SMS reminders for every existing account.

Revision ID: 20260815_0200
Revises: 20260814_0199
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0200"
down_revision = "20260814_0199"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "lesson_reminder_sms_opt_in",
        server_default=sa.text("false"),
    )
    op.execute(
        sa.text(
            """
            UPDATE users
            SET lesson_reminder_sms_opt_in = false
            WHERE lesson_reminder_sms_opt_in = true
            """
        )
    )


def downgrade() -> None:
    # The accounts that had explicitly opted in cannot be distinguished from
    # accounts enabled implicitly by the former registration behavior.
    pass
