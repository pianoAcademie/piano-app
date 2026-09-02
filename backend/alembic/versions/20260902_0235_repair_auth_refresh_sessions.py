"""Repair refresh-session schema when an already-applied branch skipped 0233."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260902_0235"
down_revision = "20260901_0234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "auth_refresh_sessions" in sa.inspect(bind).get_table_names():
        return

    op.create_table(
        "auth_refresh_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_refresh_sessions_user_id", "auth_refresh_sessions", ["user_id"], unique=False)
    op.create_index("ix_auth_refresh_sessions_token_hash", "auth_refresh_sessions", ["token_hash"], unique=True)
    op.create_index("ix_auth_refresh_sessions_expires_at", "auth_refresh_sessions", ["expires_at"], unique=False)
    op.create_index("ix_auth_refresh_sessions_revoked_at", "auth_refresh_sessions", ["revoked_at"], unique=False)


def downgrade() -> None:
    # Revision 0233 owns this table. Downgrading the repair must preserve the
    # schema expected at revision 0234.
    pass
