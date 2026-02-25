"""Add activity reference fields and planning activity mapping

Revision ID: 20260213_0013
Revises: 20260213_0012
Create Date: 2026-02-13 18:10:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260213_0013"
down_revision: Union[str, None] = "20260213_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("course_types", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "course_types",
        sa.Column("color_hex", sa.String(length=7), nullable=False, server_default=sa.text("'#94C973'")),
    )
    op.create_check_constraint(
        "ck_course_types_color_hex_length",
        "course_types",
        "char_length(color_hex) = 7",
    )

    op.execute(
        """
        UPDATE course_types
        SET description = CASE code
            WHEN 'PIANO_GROUP_ONSITE_1H' THEN 'Cours collectif de piano en presentiel (1h)'
            WHEN 'PIANO_GROUP_ONLINE_1H' THEN 'Cours collectif de piano en ligne (1h)'
            WHEN 'SOLFEGE_ONLINE_30M' THEN 'Cours de solfege en ligne (30mn)'
            WHEN 'STUDIO_REHEARSAL' THEN 'Reservation de studio de repetition'
            ELSE description
        END,
        color_hex = CASE code
            WHEN 'PIANO_GROUP_ONSITE_1H' THEN '#94C973'
            WHEN 'PIANO_GROUP_ONLINE_1H' THEN '#6FB8C8'
            WHEN 'SOLFEGE_ONLINE_30M' THEN '#F1B15B'
            WHEN 'STUDIO_REHEARSAL' THEN '#C47AA6'
            ELSE '#94C973'
        END
        """
    )

    op.create_table(
        "planning_course_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("location_id", "course_type_id", name="uq_planning_course_types_location_course_type"),
        sa.CheckConstraint("display_order >= 0", name="ck_planning_course_types_display_order_non_negative"),
    )
    op.create_index(
        "idx_planning_course_types_location_display",
        "planning_course_types",
        ["location_id", "display_order"],
        unique=False,
    )
    op.create_index(
        "idx_planning_course_types_course_type",
        "planning_course_types",
        ["course_type_id"],
        unique=False,
    )

    op.execute(
        """
        WITH ranked_course_types AS (
            SELECT
                id,
                row_number() OVER (ORDER BY name ASC, code ASC) - 1 AS pos
            FROM course_types
            WHERE active = true
        )
        INSERT INTO planning_course_types (location_id, course_type_id, display_order)
        SELECT l.id, r.id, r.pos
        FROM locations l
        CROSS JOIN ranked_course_types r
        ON CONFLICT (location_id, course_type_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_planning_course_types_course_type", table_name="planning_course_types")
    op.drop_index("idx_planning_course_types_location_display", table_name="planning_course_types")
    op.drop_table("planning_course_types")

    op.drop_constraint("ck_course_types_color_hex_length", "course_types", type_="check")
    op.drop_column("course_types", "color_hex")
    op.drop_column("course_types", "description")
