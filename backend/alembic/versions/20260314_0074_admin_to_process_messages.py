"""extend teacher statement messages for admin to-process inbox

Revision ID: 20260314_0074
Revises: 20260313_0073
Create Date: 2026-03-14 09:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260314_0074"
down_revision: Union[str, None] = "20260313_0073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("teacher_statement_messages", "statement_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)

    op.add_column(
        "teacher_statement_messages",
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'releves_professeur'")),
    )
    op.add_column(
        "teacher_statement_messages",
        sa.Column("message_type", sa.Text(), nullable=False, server_default=sa.text("'erreur_releve'")),
    )
    op.add_column(
        "teacher_statement_messages",
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("teacher_statement_messages", sa.Column("related_entity_type", sa.Text(), nullable=True))
    op.add_column("teacher_statement_messages", sa.Column("related_entity_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("teacher_statement_messages", sa.Column("handled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "teacher_statement_messages",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_foreign_key(
        "fk_teacher_statement_messages_handled_by_user_id",
        "teacher_statement_messages",
        "users",
        ["handled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE teacher_statement_messages
        SET status = CASE
            WHEN status = 'open' THEN 'a_traiter'
            WHEN status IN ('a_traiter', 'en_cours', 'termine') THEN status
            ELSE 'a_traiter'
        END,
        message_type = CASE
            WHEN message ILIKE 'Signalement prestation manquante%' THEN 'prestation_manquante'
            WHEN message ILIKE 'Probleme sur prestations selectionnees%' THEN 'erreur_lignes_releve'
            ELSE 'erreur_releve'
        END,
        source = 'releves_professeur',
        related_entity_type = 'teacher_monthly_statement',
        related_entity_id = statement_id,
        updated_at = COALESCE(created_at, now())
        """
    )

    op.create_index(
        "ix_teacher_statement_messages_status_created",
        "teacher_statement_messages",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_teacher_statement_messages_source_type_created",
        "teacher_statement_messages",
        ["source", "message_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_teacher_statement_messages_teacher_created",
        "teacher_statement_messages",
        ["teacher_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_statement_messages_teacher_created", table_name="teacher_statement_messages")
    op.drop_index("ix_teacher_statement_messages_source_type_created", table_name="teacher_statement_messages")
    op.drop_index("ix_teacher_statement_messages_status_created", table_name="teacher_statement_messages")

    op.execute(
        """
        UPDATE teacher_statement_messages
        SET status = CASE
            WHEN status = 'a_traiter' THEN 'open'
            ELSE status
        END
        """
    )

    op.drop_constraint(
        "fk_teacher_statement_messages_handled_by_user_id",
        "teacher_statement_messages",
        type_="foreignkey",
    )
    op.drop_column("teacher_statement_messages", "updated_at")
    op.drop_column("teacher_statement_messages", "handled_by_user_id")
    op.drop_column("teacher_statement_messages", "related_entity_id")
    op.drop_column("teacher_statement_messages", "related_entity_type")
    op.drop_column("teacher_statement_messages", "metadata")
    op.drop_column("teacher_statement_messages", "message_type")
    op.drop_column("teacher_statement_messages", "source")

    op.alter_column("teacher_statement_messages", "statement_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
