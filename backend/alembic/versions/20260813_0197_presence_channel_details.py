"""Distinguish native apps, installed web apps, and browser devices.

Revision ID: 20260813_0197
Revises: 20260813_0196
"""

from alembic import op


revision = "20260813_0197"
down_revision = "20260813_0196"
branch_labels = None
depends_on = None


CHANNEL_VALUES = "'WEB', 'MOBILE_APP', 'WEB_DESKTOP', 'WEB_MOBILE', 'INSTALLED_WEB', 'NATIVE_APP'"


def upgrade() -> None:
    op.drop_constraint("ck_user_presences_channel", "user_presences", type_="check")
    op.create_check_constraint(
        "ck_user_presences_channel",
        "user_presences",
        f"channel IN ({CHANNEL_VALUES})",
    )
    op.drop_constraint("ck_user_presence_hours_channel", "user_presence_hours", type_="check")
    op.create_check_constraint(
        "ck_user_presence_hours_channel",
        "user_presence_hours",
        f"channel IN ({CHANNEL_VALUES})",
    )


def downgrade() -> None:
    op.execute("DELETE FROM user_presence_hours WHERE channel NOT IN ('WEB', 'MOBILE_APP')")
    op.execute("DELETE FROM user_presences WHERE channel NOT IN ('WEB', 'MOBILE_APP')")
    op.execute("UPDATE users SET last_seen_channel = NULL WHERE last_seen_channel NOT IN ('WEB', 'MOBILE_APP')")
    op.drop_constraint("ck_user_presence_hours_channel", "user_presence_hours", type_="check")
    op.create_check_constraint(
        "ck_user_presence_hours_channel",
        "user_presence_hours",
        "channel IN ('WEB', 'MOBILE_APP')",
    )
    op.drop_constraint("ck_user_presences_channel", "user_presences", type_="check")
    op.create_check_constraint(
        "ck_user_presences_channel",
        "user_presences",
        "channel IN ('WEB', 'MOBILE_APP')",
    )
