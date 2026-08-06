"""Add mobile devices and push notification delivery tracking.

Revision ID: 20260806_0185
Revises: 20260806_0184
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260806_0185"
down_revision = "20260806_0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_push_devices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("app_target", sa.String(length=20), nullable=False, server_default=sa.text("'CLIENT'")),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("installation_id", sa.String(length=128), nullable=False),
        sa.Column("push_token", sa.String(length=512), nullable=False),
        sa.Column("permission_status", sa.String(length=30), nullable=False, server_default=sa.text("'GRANTED'")),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default=sa.text("'fr'")),
        sa.Column("app_version", sa.String(length=40), nullable=True),
        sa.Column("device_label", sa.String(length=120), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "app_target",
            "installation_id",
            name="uq_mobile_push_devices_target_installation",
        ),
        sa.UniqueConstraint(
            "app_target",
            "push_token",
            name="uq_mobile_push_devices_target_token",
        ),
    )
    op.create_index(
        "ix_mobile_push_devices_user_enabled",
        "mobile_push_devices",
        ["user_id", "is_enabled"],
    )

    op.add_column(
        "notifications",
        sa.Column(
            "recipient_device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mobile_push_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("notifications", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notifications", sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_notifications_recipient_device_id", "notifications", ["recipient_device_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_device_id", table_name="notifications")
    op.drop_column("notifications", "opened_at")
    op.drop_column("notifications", "received_at")
    op.drop_column("notifications", "recipient_device_id")
    op.drop_index("ix_mobile_push_devices_user_enabled", table_name="mobile_push_devices")
    op.drop_table("mobile_push_devices")
