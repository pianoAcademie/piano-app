"""add legal_entities and seller legal entity fks

Revision ID: 20260306_0053
Revises: 20260306_0052
Create Date: 2026-03-06 18:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260306_0053"
down_revision: Union[str, None] = "20260306_0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legal_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("siren", sa.Text(), nullable=True),
        sa.Column("siret", sa.Text(), nullable=True),
        sa.Column("vat_number", sa.Text(), nullable=True),
        sa.Column("address_text", sa.Text(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default=sa.text("'FR'")),
        sa.Column("invoice_prefix", sa.String(length=20), nullable=False),
        sa.Column("invoice_next_number", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "course_types",
        sa.Column("seller_legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_course_types_seller_legal_entity_id",
        "course_types",
        "legal_entities",
        ["seller_legal_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_course_types_seller_legal_entity_id", "course_types", ["seller_legal_entity_id"], unique=False)

    op.add_column(
        "course_sessions",
        sa.Column("snapshot_seller_legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_course_sessions_snapshot_seller_legal_entity_id",
        "course_sessions",
        "legal_entities",
        ["snapshot_seller_legal_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_course_sessions_snapshot_seller_legal_entity_id",
        "course_sessions",
        ["snapshot_seller_legal_entity_id"],
        unique=False,
    )

    op.add_column(
        "client_invoice_lines",
        sa.Column("seller_legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_client_invoice_lines_seller_legal_entity_id",
        "client_invoice_lines",
        "legal_entities",
        ["seller_legal_entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_client_invoice_lines_seller_legal_entity_id",
        "client_invoice_lines",
        ["seller_legal_entity_id"],
        unique=False,
    )

    # Seed legal entities (idempotent by name).
    op.execute(
        """
        INSERT INTO legal_entities (
            name,
            siren,
            siret,
            vat_number,
            address_text,
            country_code,
            invoice_prefix,
            invoice_next_number,
            is_active,
            created_at,
            updated_at
        )
        SELECT
            'PIANO ACADEMIE',
            '828051417',
            '82805141700032',
            'FR74828051417',
            NULL,
            'FR',
            'PA',
            1,
            true,
            now(),
            now()
        WHERE NOT EXISTS (
            SELECT 1 FROM legal_entities WHERE name = 'PIANO ACADEMIE'
        )
        """
    )
    op.execute(
        """
        INSERT INTO legal_entities (
            name,
            siren,
            siret,
            vat_number,
            address_text,
            country_code,
            invoice_prefix,
            invoice_next_number,
            is_active,
            created_at,
            updated_at
        )
        SELECT
            'PIANO ACADEMIE SERVICES',
            '828163865',
            '82816386500011',
            'FR52828163865',
            NULL,
            'FR',
            'PAS',
            1,
            true,
            now(),
            now()
        WHERE NOT EXISTS (
            SELECT 1 FROM legal_entities WHERE name = 'PIANO ACADEMIE SERVICES'
        )
        """
    )

    # Backfill FKs from existing legacy text codes.
    op.execute(
        """
        UPDATE course_types AS ct
        SET seller_legal_entity_id = le.id
        FROM legal_entities AS le
        WHERE ct.seller_legal_entity_id IS NULL
          AND UPPER(TRIM(COALESCE(ct.billing_entity_code, ''))) = 'PIANO_ACADEMIE'
          AND le.name = 'PIANO ACADEMIE'
        """
    )
    op.execute(
        """
        UPDATE course_types AS ct
        SET seller_legal_entity_id = le.id
        FROM legal_entities AS le
        WHERE ct.seller_legal_entity_id IS NULL
          AND UPPER(TRIM(COALESCE(ct.billing_entity_code, ''))) = 'PIANO_ACADEMIE_SERVICES'
          AND le.name = 'PIANO ACADEMIE SERVICES'
        """
    )

    op.execute(
        """
        UPDATE course_sessions AS cs
        SET snapshot_seller_legal_entity_id = le.id
        FROM legal_entities AS le
        WHERE cs.snapshot_seller_legal_entity_id IS NULL
          AND UPPER(TRIM(COALESCE(cs.billing_entity_snapshot, ''))) = 'PIANO_ACADEMIE'
          AND le.name = 'PIANO ACADEMIE'
        """
    )
    op.execute(
        """
        UPDATE course_sessions AS cs
        SET snapshot_seller_legal_entity_id = le.id
        FROM legal_entities AS le
        WHERE cs.snapshot_seller_legal_entity_id IS NULL
          AND UPPER(TRIM(COALESCE(cs.billing_entity_snapshot, ''))) = 'PIANO_ACADEMIE_SERVICES'
          AND le.name = 'PIANO ACADEMIE SERVICES'
        """
    )

    # Secondary backfill: align sessions with their course type FK when snapshot text is missing/unknown.
    op.execute(
        """
        UPDATE course_sessions AS cs
        SET snapshot_seller_legal_entity_id = ct.seller_legal_entity_id
        FROM course_types AS ct
        WHERE cs.snapshot_seller_legal_entity_id IS NULL
          AND cs.course_type_id = ct.id
          AND ct.seller_legal_entity_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE client_invoice_lines AS cil
        SET seller_legal_entity_id = le.id
        FROM legal_entities AS le
        WHERE cil.seller_legal_entity_id IS NULL
          AND UPPER(TRIM(COALESCE(cil.billing_entity, ''))) = 'PIANO_ACADEMIE'
          AND le.name = 'PIANO ACADEMIE'
        """
    )
    op.execute(
        """
        UPDATE client_invoice_lines AS cil
        SET seller_legal_entity_id = le.id
        FROM legal_entities AS le
        WHERE cil.seller_legal_entity_id IS NULL
          AND UPPER(TRIM(COALESCE(cil.billing_entity, ''))) = 'PIANO_ACADEMIE_SERVICES'
          AND le.name = 'PIANO ACADEMIE SERVICES'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_client_invoice_lines_seller_legal_entity_id", table_name="client_invoice_lines")
    op.drop_constraint("fk_client_invoice_lines_seller_legal_entity_id", "client_invoice_lines", type_="foreignkey")
    op.drop_column("client_invoice_lines", "seller_legal_entity_id")

    op.drop_index("ix_course_sessions_snapshot_seller_legal_entity_id", table_name="course_sessions")
    op.drop_constraint("fk_course_sessions_snapshot_seller_legal_entity_id", "course_sessions", type_="foreignkey")
    op.drop_column("course_sessions", "snapshot_seller_legal_entity_id")

    op.drop_index("ix_course_types_seller_legal_entity_id", table_name="course_types")
    op.drop_constraint("fk_course_types_seller_legal_entity_id", "course_types", type_="foreignkey")
    op.drop_column("course_types", "seller_legal_entity_id")

    op.drop_table("legal_entities")
