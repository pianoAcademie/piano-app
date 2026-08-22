"""Allow up to four professors on Masterclass sessions.

Revision ID: 20260822_0205
Revises: 20260820_0204
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260822_0205"
down_revision = "20260820_0204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_session_professors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position >= 1 AND position <= 4", name="ck_course_session_professors_position"),
        sa.ForeignKeyConstraint(["professor_id"], ["professors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["course_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "position", name="uq_course_session_professors_session_position"),
        sa.UniqueConstraint("session_id", "professor_id", name="uq_course_session_professors_session_professor"),
    )
    op.create_index(
        op.f("ix_course_session_professors_session_id"),
        "course_session_professors",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_course_session_professors_professor_id"),
        "course_session_professors",
        ["professor_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO course_session_professors (session_id, professor_id, position)
            SELECT id, professor_id, 1
            FROM course_sessions
            WHERE professor_id IS NOT NULL
            ON CONFLICT (session_id, professor_id) DO NOTHING
            """
        )
    )

    op.drop_constraint(
        "professor_session_payouts_session_id_key",
        "professor_session_payouts",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_professor_session_payout_session_professor",
        "professor_session_payouts",
        ["session_id", "professor_id"],
    )

    op.add_column(
        "planning_simulation_teacher_assignments",
        sa.Column("position", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.drop_constraint(
        "uq_planning_simulation_teacher_assignment_slot",
        "planning_simulation_teacher_assignments",
        type_="unique",
    )
    op.create_check_constraint(
        "ck_planning_simulation_teacher_assignment_position",
        "planning_simulation_teacher_assignments",
        "position >= 1 AND position <= 4",
    )
    op.create_unique_constraint(
        "uq_planning_simulation_teacher_assignment_slot_position",
        "planning_simulation_teacher_assignments",
        ["school_year_label", "slot_key", "position"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_planning_simulation_teacher_assignment_slot_position",
        "planning_simulation_teacher_assignments",
        type_="unique",
    )
    op.drop_constraint(
        "ck_planning_simulation_teacher_assignment_position",
        "planning_simulation_teacher_assignments",
        type_="check",
    )
    op.create_unique_constraint(
        "uq_planning_simulation_teacher_assignment_slot",
        "planning_simulation_teacher_assignments",
        ["school_year_label", "slot_key"],
    )
    op.drop_column("planning_simulation_teacher_assignments", "position")

    op.drop_constraint(
        "uq_professor_session_payout_session_professor",
        "professor_session_payouts",
        type_="unique",
    )
    op.create_unique_constraint(
        "professor_session_payouts_session_id_key",
        "professor_session_payouts",
        ["session_id"],
    )
    op.drop_index(op.f("ix_course_session_professors_professor_id"), table_name="course_session_professors")
    op.drop_index(op.f("ix_course_session_professors_session_id"), table_name="course_session_professors")
    op.drop_table("course_session_professors")
