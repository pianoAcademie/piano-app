"""Persist provisional teacher assignments for planning simulations.

Revision ID: 20260815_0201
Revises: 20260815_0200
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260815_0201"
down_revision = "20260815_0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planning_simulation_teacher_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("school_year_label", sa.String(length=20), nullable=False),
        sa.Column("slot_key", sa.String(length=600), nullable=False),
        sa.Column(
            "professor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("teacher_label", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'PREVISIONAL'")),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "school_year_label",
            "slot_key",
            name="uq_planning_simulation_teacher_assignment_slot",
        ),
        sa.CheckConstraint(
            "status IN ('PREVISIONAL', 'CONFIRMED')",
            name="ck_planning_simulation_teacher_assignment_status",
        ),
    )
    op.create_index(
        "ix_planning_simulation_teacher_assignments_school_year_label",
        "planning_simulation_teacher_assignments",
        ["school_year_label"],
    )
    op.create_index(
        "ix_planning_simulation_teacher_assignments_professor_id",
        "planning_simulation_teacher_assignments",
        ["professor_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_planning_simulation_teacher_assignments_professor_id",
        table_name="planning_simulation_teacher_assignments",
    )
    op.drop_index(
        "ix_planning_simulation_teacher_assignments_school_year_label",
        table_name="planning_simulation_teacher_assignments",
    )
    op.drop_table("planning_simulation_teacher_assignments")
