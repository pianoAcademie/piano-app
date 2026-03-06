"""Add professor pay grid periods and brackets

Revision ID: 20260312_0066
Revises: 20260312_0065
Create Date: 2026-03-12 14:20:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260312_0066"
down_revision: Union[str, None] = "20260312_0065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "professor_pay_grid_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_professor_pay_grid_period_dates"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_professor_pay_grid_periods_status_start", "professor_pay_grid_periods", ["status", "start_date"], unique=False)

    op.create_table(
        "professor_pay_grid_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default=sa.text("'AUTRE'")),
        sa.Column("reference_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("default_hourly_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("default_hourly_rate IS NULL OR default_hourly_rate >= 0", name="ck_professor_pay_grid_rules_default_rate_non_negative"),
        sa.ForeignKeyConstraint(["period_id"], ["professor_pay_grid_periods.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_type_id"], ["course_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_id", "course_type_id", name="uq_professor_pay_grid_rules_period_course_type"),
    )
    op.create_index("ix_professor_pay_grid_rules_period_sort", "professor_pay_grid_rules", ["period_id", "sort_order"], unique=False)

    op.create_table(
        "professor_pay_grid_brackets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("min_students", sa.Integer(), nullable=False),
        sa.Column("max_students", sa.Integer(), nullable=True),
        sa.Column("hourly_rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("min_students >= 0", name="ck_professor_pay_grid_brackets_min_non_negative"),
        sa.CheckConstraint("max_students IS NULL OR max_students >= min_students", name="ck_professor_pay_grid_brackets_range"),
        sa.CheckConstraint("hourly_rate >= 0", name="ck_professor_pay_grid_brackets_rate_non_negative"),
        sa.ForeignKeyConstraint(["rule_id"], ["professor_pay_grid_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_professor_pay_grid_brackets_rule_sort", "professor_pay_grid_brackets", ["rule_id", "sort_order"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_professor_pay_grid_brackets_rule_sort", table_name="professor_pay_grid_brackets")
    op.drop_table("professor_pay_grid_brackets")

    op.drop_index("ix_professor_pay_grid_rules_period_sort", table_name="professor_pay_grid_rules")
    op.drop_table("professor_pay_grid_rules")

    op.drop_index("ix_professor_pay_grid_periods_status_start", table_name="professor_pay_grid_periods")
    op.drop_table("professor_pay_grid_periods")
