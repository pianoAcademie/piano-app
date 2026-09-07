"""Add annual series transfer priority requests.

Revision ID: 20260907_0248
Revises: 20260906_0247
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260907_0248"
down_revision = "20260906_0247"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "annual_series_transfer_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_recurrence_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_recurrence_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'WAITING'"), nullable=False),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_booking_id"], ["bookings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_session_id"], ["course_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_annual_series_transfer_open_priority",
        "annual_series_transfer_requests",
        ["status", "target_recurrence_group_id", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_annual_series_transfer_open_priority", table_name="annual_series_transfer_requests")
    op.drop_table("annual_series_transfer_requests")
