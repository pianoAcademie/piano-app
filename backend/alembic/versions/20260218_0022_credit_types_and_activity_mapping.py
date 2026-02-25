"""credit types referential and strict activity mapping

Revision ID: 20260218_0022
Revises: 20260217_0021
Create Date: 2026-02-18 23:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260218_0022"
down_revision: Union[str, None] = "20260217_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_credit_types_code"),
    )
    op.create_index("ix_credit_types_active", "credit_types", ["active"], unique=False)

    op.add_column("course_types", sa.Column("credit_type_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_course_types_credit_type_id",
        "course_types",
        "credit_types",
        ["credit_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_course_types_credit_type_id", "course_types", ["credit_type_id"], unique=False)

    op.execute(
        """
        INSERT INTO credit_types (code, name, description)
        VALUES
            ('CREDIT_PIANO_ONSITE', 'Credit cours de piano en presentiel', 'Credits utilises pour les cours de piano en presentiel'),
            ('CREDIT_PIANO_ONLINE', 'Credit cours de piano en ligne', 'Credits utilises pour les cours de piano en ligne'),
            ('CREDIT_SOLFEGE_ONSITE', 'Credit cours de solfege en presentiel', 'Credits utilises pour les cours de solfege en presentiel'),
            ('CREDIT_SOLFEGE_ONLINE', 'Credit cours de solfege en ligne', 'Credits utilises pour les cours de solfege en ligne'),
            ('CREDIT_ALLO_PIANO_30', 'Credit Allo Piano (30 minutes)', 'Credits utilises pour les sessions Allo Piano 30mn'),
            ('CREDIT_STUDIO', 'Credit reservation studio', 'Credits utilises pour les reservations de studio'),
            ('CREDIT_CONTROLE', 'Credit cours de controle', 'Credits utilises pour les cours de controle'),
            ('CREDIT_MASTERCLASS', 'Credit masterclass', 'Credits utilises pour les masterclass'),
            ('CREDIT_PARTICULIER', 'Credit cours particulier', 'Credits utilises pour les cours particuliers'),
            ('CREDIT_EVEIL_MUSICAL', 'Credit cours d eveil musical', 'Credits utilises pour les cours d eveil musical')
        ON CONFLICT (code) DO NOTHING
        """
    )

    op.execute(
        """
        WITH type_match AS (
            SELECT
                ct.id AS course_type_id,
                CASE
                    WHEN upper(ct.code) LIKE '%STUDIO%' OR upper(ct.service_code) LIKE '%STUDIO%' OR lower(ct.name) LIKE '%studio%' THEN 'CREDIT_STUDIO'
                    WHEN upper(ct.code) LIKE '%ALLO_PIANO%' OR upper(ct.service_code) = 'ALLO_PIANO' OR lower(ct.name) LIKE '%allo piano%' THEN 'CREDIT_ALLO_PIANO_30'
                    WHEN upper(ct.code) LIKE '%MASTERCLASS%' OR upper(ct.service_code) = 'MASTERCLASS' OR lower(ct.name) LIKE '%masterclass%' THEN 'CREDIT_MASTERCLASS'
                    WHEN upper(ct.code) LIKE '%PARTICULIER%' OR upper(ct.service_code) LIKE '%PARTICULIER%' OR lower(ct.name) LIKE '%particulier%' THEN 'CREDIT_PARTICULIER'
                    WHEN upper(ct.code) LIKE '%EVEIL%' OR upper(ct.service_code) LIKE '%EVEIL%' OR lower(ct.name) LIKE '%eveil%' THEN 'CREDIT_EVEIL_MUSICAL'
                    WHEN upper(ct.code) LIKE '%CONTROLE%' OR upper(ct.service_code) LIKE '%CONTROLE%' OR lower(ct.name) LIKE '%controle%' THEN 'CREDIT_CONTROLE'
                    WHEN upper(ct.code) LIKE '%SOLFEGE%' AND ct.mode = 'ONSITE'::delivery_mode THEN 'CREDIT_SOLFEGE_ONSITE'
                    WHEN upper(ct.code) LIKE '%SOLFEGE%' AND ct.mode = 'ONLINE'::delivery_mode THEN 'CREDIT_SOLFEGE_ONLINE'
                    WHEN upper(ct.service_code) = 'SOLFEGE' AND ct.mode = 'ONSITE'::delivery_mode THEN 'CREDIT_SOLFEGE_ONSITE'
                    WHEN upper(ct.service_code) = 'SOLFEGE' AND ct.mode = 'ONLINE'::delivery_mode THEN 'CREDIT_SOLFEGE_ONLINE'
                    WHEN lower(ct.name) LIKE '%solfege%' AND lower(ct.name) LIKE '%presentiel%' THEN 'CREDIT_SOLFEGE_ONSITE'
                    WHEN lower(ct.name) LIKE '%solfege%' AND lower(ct.name) LIKE '%ligne%' THEN 'CREDIT_SOLFEGE_ONLINE'
                    WHEN upper(ct.code) LIKE '%PIANO_GROUP_ONSITE%' OR upper(ct.code) LIKE '%PIANO_GROUP_PRESENTIEL%' THEN 'CREDIT_PIANO_ONSITE'
                    WHEN upper(ct.code) LIKE '%PIANO_GROUP_ONLINE%' OR upper(ct.code) LIKE '%PIANO_GROUP_LIGNE%' THEN 'CREDIT_PIANO_ONLINE'
                    WHEN upper(ct.service_code) = 'PIANO_CLASS' AND ct.mode = 'ONSITE'::delivery_mode THEN 'CREDIT_PIANO_ONSITE'
                    WHEN upper(ct.service_code) = 'PIANO_CLASS' AND ct.mode = 'ONLINE'::delivery_mode THEN 'CREDIT_PIANO_ONLINE'
                    WHEN lower(ct.name) LIKE '%piano%' AND lower(ct.name) LIKE '%presentiel%' THEN 'CREDIT_PIANO_ONSITE'
                    WHEN lower(ct.name) LIKE '%piano%' AND lower(ct.name) LIKE '%ligne%' THEN 'CREDIT_PIANO_ONLINE'
                    ELSE NULL
                END AS credit_type_code
            FROM course_types ct
        )
        UPDATE course_types ct
        SET credit_type_id = c.id
        FROM type_match tm
        JOIN credit_types c ON c.code = tm.credit_type_code
        WHERE ct.id = tm.course_type_id
          AND tm.credit_type_code IS NOT NULL
          AND ct.credit_type_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_course_types_credit_type_id", table_name="course_types")
    op.drop_constraint("fk_course_types_credit_type_id", "course_types", type_="foreignkey")
    op.drop_column("course_types", "credit_type_id")

    op.drop_index("ix_credit_types_active", table_name="credit_types")
    op.drop_table("credit_types")
