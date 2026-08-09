"""Store hourly user-presence history.

Revision ID: 20260809_0192
Revises: 20260808_0191
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0192"
down_revision = "20260808_0191"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_presence_hours",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("hour_started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("channel IN ('WEB', 'MOBILE_APP')", name="ck_user_presence_hours_channel"),
        sa.CheckConstraint("heartbeat_count >= 1", name="ck_user_presence_hours_heartbeat_count"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "channel",
            "hour_started_at_utc",
            name="uq_user_presence_hours_user_channel_hour",
        ),
    )
    op.create_index(
        "ix_user_presence_hours_hour_started_at_utc",
        "user_presence_hours",
        ["hour_started_at_utc"],
    )
    op.execute(
        """
        INSERT INTO user_presence_hours (
            user_id, channel, hour_started_at_utc, first_seen_at, last_seen_at,
            heartbeat_count, created_at, updated_at
        )
        SELECT
            user_id,
            channel,
            date_trunc('hour', last_seen_at),
            last_seen_at,
            last_seen_at,
            1,
            now(),
            now()
        FROM user_presences
        ON CONFLICT (user_id, channel, hour_started_at_utc) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_presence_hours_hour_started_at_utc", table_name="user_presence_hours")
    op.drop_table("user_presence_hours")
