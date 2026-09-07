"""Add explicit simulation-to-production teacher synchronization history.

Revision ID: 20260906_0247
Revises: 20260905_0246
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260906_0247"
down_revision = "20260905_0246"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planning_simulation_teacher_assignments",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "planning_simulation_teacher_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("school_year_label", sa.String(length=20), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'APPLIED'"), nullable=False),
        sa.Column("change_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("session_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("rollback_note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rolled_back_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rolled_back_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_planning_teacher_sync_runs_school_year",
        "planning_simulation_teacher_sync_runs",
        ["school_year_label", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_planning_teacher_sync_runs_school_year", table_name="planning_simulation_teacher_sync_runs")
    op.drop_table("planning_simulation_teacher_sync_runs")
    op.drop_column("planning_simulation_teacher_assignments", "deleted_at")
