"""professor daily schedule settings and archived group messages

Revision ID: 20260217_0021
Revises: 20260217_0020
Create Date: 2026-02-17 16:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260217_0021"
down_revision: Union[str, None] = "20260217_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professors",
        sa.Column("daily_schedule_email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professors",
        sa.Column("daily_schedule_email_time", sa.String(length=5), nullable=False, server_default=sa.text("'07:00'")),
    )
    op.add_column(
        "professors",
        sa.Column("daily_schedule_skip_if_no_course", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "professors",
        sa.Column("last_daily_schedule_sent_on", sa.Date(), nullable=True),
    )

    op.create_check_constraint(
        "ck_professors_daily_schedule_email_time_hhmm",
        "professors",
        "daily_schedule_email_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'",
    )

    op.execute("CREATE TYPE message_format AS ENUM ('TEXT', 'HTML')")
    op.create_table(
        "professor_session_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "body_format",
            postgresql.ENUM("TEXT", "HTML", name="message_format", create_type=False),
            nullable=False,
            server_default=sa.text("'TEXT'::message_format"),
        ),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["session_id"], ["course_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["professor_id"], ["professors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_professor_session_messages_professor_sent_at",
        "professor_session_messages",
        ["professor_id", "sent_at"],
        unique=False,
    )
    op.create_index(
        "ix_professor_session_messages_session_id",
        "professor_session_messages",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_professor_session_messages_session_id", table_name="professor_session_messages")
    op.drop_index("ix_professor_session_messages_professor_sent_at", table_name="professor_session_messages")
    op.drop_table("professor_session_messages")
    op.execute("DROP TYPE message_format")

    op.drop_constraint("ck_professors_daily_schedule_email_time_hhmm", "professors", type_="check")
    op.drop_column("professors", "last_daily_schedule_sent_on")
    op.drop_column("professors", "daily_schedule_skip_if_no_course")
    op.drop_column("professors", "daily_schedule_email_time")
    op.drop_column("professors", "daily_schedule_email_enabled")
