"""Track user login and online presence.

Revision ID: 20260808_0189
Revises: 20260808_0188
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_0189"
down_revision = "20260808_0188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_seen_channel", sa.String(length=20), nullable=True))
    op.create_index("ix_users_last_login_at", "users", ["last_login_at"])
    op.create_index("ix_users_last_seen_at", "users", ["last_seen_at"])

    op.create_table(
        "user_presences",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("channel IN ('WEB', 'MOBILE_APP')", name="ck_user_presences_channel"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "channel", name="uq_user_presences_user_channel"),
    )
    op.create_index("ix_user_presences_last_seen_at", "user_presences", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_user_presences_last_seen_at", table_name="user_presences")
    op.drop_table("user_presences")
    op.drop_index("ix_users_last_seen_at", table_name="users")
    op.drop_index("ix_users_last_login_at", table_name="users")
    op.drop_column("users", "last_seen_channel")
    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "last_login_at")
