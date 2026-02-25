"""link professor contract lines to backoffice activities

Revision ID: 20260225_0032
Revises: 20260224_0031
Create Date: 2026-02-25 10:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260225_0032"
down_revision: Union[str, None] = "20260224_0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professor_contract_grid_lines",
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_prof_ctr_grid_lines_course_type",
        "professor_contract_grid_lines",
        "course_types",
        ["course_type_id"],
        ["id"],
    )
    op.create_index(
        "ix_prof_ctr_grid_lines_grid_course_type",
        "professor_contract_grid_lines",
        ["grid_id", "course_type_id"],
        unique=False,
    )

    op.execute(
        """
        UPDATE professor_contract_grid_lines AS l
        SET course_type_id = (
            SELECT ct.id
            FROM course_types AS ct
            WHERE lower(trim(ct.name)) = lower(trim(l.service_type))
              AND (
                  (l.mode = 'PRESENTIEL' AND ct.mode = 'ONSITE')
                  OR (l.mode = 'EN_LIGNE' AND ct.mode = 'ONLINE')
                  OR (l.mode = 'AUTRE' AND ct.mode = 'ANY')
                  OR ct.mode = 'ANY'
              )
            ORDER BY
              CASE
                WHEN l.mode = 'PRESENTIEL' AND ct.mode = 'ONSITE' THEN 0
                WHEN l.mode = 'EN_LIGNE' AND ct.mode = 'ONLINE' THEN 0
                WHEN l.mode = 'AUTRE' AND ct.mode = 'ANY' THEN 0
                WHEN ct.mode = 'ANY' THEN 1
                ELSE 2
              END,
              ct.created_at ASC,
              ct.id ASC
            LIMIT 1
        )
        WHERE l.course_type_id IS NULL;
        """
    )

    op.execute(
        """
        UPDATE professor_contract_grid_lines AS l
        SET service_type = ct.name,
            reference_duration_minutes = ct.duration_minutes,
            mode = (
                CASE
                    WHEN ct.mode = 'ONLINE' THEN 'EN_LIGNE'
                    WHEN ct.mode = 'ONSITE' THEN 'PRESENTIEL'
                    ELSE 'AUTRE'
                END
            )::professor_contract_line_mode
        FROM course_types AS ct
        WHERE l.course_type_id = ct.id;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_prof_ctr_grid_lines_grid_course_type", table_name="professor_contract_grid_lines")
    op.drop_constraint(
        "fk_prof_ctr_grid_lines_course_type",
        "professor_contract_grid_lines",
        type_="foreignkey",
    )
    op.drop_column("professor_contract_grid_lines", "course_type_id")
