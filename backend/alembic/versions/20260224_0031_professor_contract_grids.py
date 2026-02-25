"""add professor contract grids and headcount rules

Revision ID: 20260224_0031
Revises: 20260224_0030
Create Date: 2026-02-24 23:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260224_0031"
down_revision: Union[str, None] = "20260224_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    line_mode = postgresql.ENUM("PRESENTIEL", "EN_LIGNE", "AUTRE", name="professor_contract_line_mode")
    line_mode.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "professor_contract_grids",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("location_code", sa.String(length=60), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["professor_id"], ["professors.id"], name="fk_professor_contract_grids_professor_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_professor_contract_grids_valid_range"),
    )
    op.create_index(
        "ix_professor_contract_grids_professor_validity",
        "professor_contract_grids",
        ["professor_id", "valid_from", "valid_to"],
        unique=False,
    )
    op.create_index(
        "ix_professor_contract_grids_professor_location",
        "professor_contract_grids",
        ["professor_id", "location_code"],
        unique=False,
    )

    op.create_table(
        "professor_contract_grid_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("grid_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("service_type", sa.String(length=255), nullable=False),
        sa.Column(
            "mode",
            postgresql.ENUM("PRESENTIEL", "EN_LIGNE", "AUTRE", name="professor_contract_line_mode", create_type=False),
            nullable=False,
        ),
        sa.Column("reference_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("default_hourly_rate", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["grid_id"], ["professor_contract_grids.id"], name="fk_professor_contract_grid_lines_grid_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("display_order >= 0", name="ck_professor_contract_grid_lines_display_order_non_negative"),
        sa.CheckConstraint(
            "reference_duration_minutes IS NULL OR reference_duration_minutes > 0",
            name="ck_professor_contract_grid_lines_duration_positive",
        ),
        sa.CheckConstraint(
            "default_hourly_rate IS NULL OR default_hourly_rate >= 0",
            name="ck_professor_contract_grid_lines_default_rate_non_negative",
        ),
    )
    op.create_index(
        "ix_professor_contract_grid_lines_grid_order",
        "professor_contract_grid_lines",
        ["grid_id", "display_order"],
        unique=False,
    )

    op.create_table(
        "professor_contract_grid_line_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("min_students", sa.Integer(), nullable=False),
        sa.Column("max_students", sa.Integer(), nullable=True),
        sa.Column("hourly_rate", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["line_id"],
            ["professor_contract_grid_lines.id"],
            name="fk_professor_contract_grid_line_rules_line_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("display_order >= 0", name="ck_prof_contract_line_rules_disp_nonneg"),
        sa.CheckConstraint("min_students >= 0", name="ck_professor_contract_grid_line_rules_min_non_negative"),
        sa.CheckConstraint(
            "max_students IS NULL OR max_students >= min_students",
            name="ck_professor_contract_grid_line_rules_max_ge_min",
        ),
        sa.CheckConstraint("hourly_rate >= 0", name="ck_professor_contract_grid_line_rules_rate_non_negative"),
    )
    op.create_index(
        "ix_professor_contract_grid_line_rules_line_order",
        "professor_contract_grid_line_rules",
        ["line_id", "display_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_professor_contract_grid_line_rules_line_order", table_name="professor_contract_grid_line_rules")
    op.drop_table("professor_contract_grid_line_rules")

    op.drop_index("ix_professor_contract_grid_lines_grid_order", table_name="professor_contract_grid_lines")
    op.drop_table("professor_contract_grid_lines")

    op.drop_index("ix_professor_contract_grids_professor_location", table_name="professor_contract_grids")
    op.drop_index("ix_professor_contract_grids_professor_validity", table_name="professor_contract_grids")
    op.drop_table("professor_contract_grids")

    line_mode = postgresql.ENUM("PRESENTIEL", "EN_LIGNE", "AUTRE", name="professor_contract_line_mode")
    line_mode.drop(op.get_bind(), checkfirst=True)
