"""Add persistent unified communication logs

Revision ID: 20260304_0046
Revises: 20260303_0045
Create Date: 2026-03-04 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260304_0046"
down_revision: Union[str, None] = "20260303_0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    communication_channel = postgresql.ENUM(
        "EMAIL",
        "SMS",
        name="communication_channel",
    )
    communication_channel.create(op.get_bind(), checkfirst=True)

    communication_sender_category = postgresql.ENUM(
        "PROFESSOR",
        "SYSTEM",
        "OTHER_USER",
        name="communication_sender_category",
    )
    communication_sender_category.create(op.get_bind(), checkfirst=True)

    communication_delivery_status = postgresql.ENUM(
        "DELIVERED",
        "SENT",
        "FAILED",
        "PENDING",
        "SKIPPED",
        "UNKNOWN",
        name="communication_delivery_status",
    )
    communication_delivery_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "communication_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "channel",
            postgresql.ENUM("EMAIL", "SMS", name="communication_channel", create_type=False),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("communication_type", sa.String(length=80), nullable=False, server_default=sa.text("'OTHER'")),
        sa.Column(
            "sender_category",
            postgresql.ENUM("PROFESSOR", "SYSTEM", "OTHER_USER", name="communication_sender_category", create_type=False),
            nullable=False,
            server_default=sa.text("'SYSTEM'::communication_sender_category"),
        ),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sender_label", sa.String(length=255), nullable=False, server_default=sa.text("'Systeme'")),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("professors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient", sa.String(length=320), nullable=False, server_default=sa.text("'-'")),
        sa.Column("subject", sa.String(length=255), nullable=False, server_default=sa.text("'Communication systeme'")),
        sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "content_format",
            postgresql.ENUM("TEXT", "HTML", name="message_format", create_type=False),
            nullable=False,
            server_default=sa.text("'TEXT'::message_format"),
        ),
        sa.Column(
            "delivery_status",
            postgresql.ENUM(
                "DELIVERED",
                "SENT",
                "FAILED",
                "PENDING",
                "SKIPPED",
                "UNKNOWN",
                name="communication_delivery_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'UNKNOWN'::communication_delivery_status"),
        ),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_message_id", sa.String(length=160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_communication_logs_occurred_at", "communication_logs", ["occurred_at"])
    op.create_index("ix_communication_logs_channel_occurred", "communication_logs", ["channel", "occurred_at"])
    op.create_index("ix_communication_logs_type", "communication_logs", ["communication_type"])
    op.create_index("ix_communication_logs_professor", "communication_logs", ["professor_id"])
    op.create_index("ix_communication_logs_provider_message_id", "communication_logs", ["provider_message_id"])

    op.execute(
        """
        INSERT INTO communication_logs (
            channel,
            source,
            communication_type,
            sender_category,
            sender_label,
            professor_id,
            recipient,
            subject,
            content,
            content_format,
            delivery_status,
            provider,
            occurred_at,
            delivered_at,
            created_at,
            updated_at
        )
        SELECT
            'EMAIL'::communication_channel,
            'PROFESSOR_SESSION_MESSAGE',
            'PROFESSOR_STUDENT',
            'PROFESSOR'::communication_sender_category,
            COALESCE(NULLIF(trim(p.first_name || ' ' || p.last_name), ''), p.email, 'Professeur'),
            p.id,
            psm.recipient_count::text || ' destinataire(s) - ' || COALESCE(cs.title, 'Session'),
            COALESCE(psm.subject, 'Communication professeur'),
            COALESCE(psm.body, ''),
            psm.body_format::message_format,
            'SENT'::communication_delivery_status,
            'LEGACY',
            COALESCE(psm.sent_at, psm.created_at, now()),
            psm.sent_at,
            COALESCE(psm.created_at, now()),
            now()
        FROM professor_session_messages psm
        JOIN professors p ON p.id = psm.professor_id
        LEFT JOIN course_sessions cs ON cs.id = psm.session_id
        """
    )

    op.execute(
        """
        INSERT INTO communication_logs (
            channel,
            source,
            communication_type,
            sender_category,
            sender_label,
            recipient_user_id,
            recipient,
            subject,
            content,
            content_format,
            delivery_status,
            provider,
            provider_message_id,
            error_message,
            occurred_at,
            delivered_at,
            failed_at,
            created_at,
            updated_at
        )
        SELECT
            'EMAIL'::communication_channel,
            'SYSTEM_EMAIL_REMINDER',
            'COURSE_REMINDER',
            'SYSTEM'::communication_sender_category,
            'Systeme',
            u.id,
            COALESCE(NULLIF(lower(trim(u.email)), ''), '-'),
            'Rappel de cours - ' || COALESCE(cs.title, 'Session'),
            COALESCE(NULLIF(er.error_message, ''), 'Rappel de cours genere automatiquement par le systeme.'),
            'TEXT'::message_format,
            CASE
                WHEN er.status = 'SENT' THEN 'DELIVERED'::communication_delivery_status
                WHEN er.status = 'FAILED' THEN 'FAILED'::communication_delivery_status
                WHEN er.status = 'SKIPPED' THEN 'SKIPPED'::communication_delivery_status
                WHEN er.status = 'PENDING' THEN 'PENDING'::communication_delivery_status
                ELSE 'UNKNOWN'::communication_delivery_status
            END,
            'LEGACY',
            er.provider_message_id,
            er.error_message,
            COALESCE(er.sent_at, er.created_at, now()),
            CASE WHEN er.status = 'SENT' THEN er.sent_at ELSE NULL END,
            CASE WHEN er.status = 'FAILED' THEN er.sent_at ELSE NULL END,
            er.created_at,
            now()
        FROM email_reminders er
        JOIN bookings b ON b.id = er.booking_id
        JOIN users u ON u.id = b.user_id
        LEFT JOIN course_sessions cs ON cs.id = b.session_id
        """
    )

    op.execute(
        """
        INSERT INTO communication_logs (
            channel,
            source,
            communication_type,
            sender_category,
            sender_user_id,
            sender_label,
            recipient_user_id,
            recipient,
            subject,
            content,
            content_format,
            delivery_status,
            provider,
            occurred_at,
            created_at,
            updated_at
        )
        SELECT
            CASE WHEN upper(cne.entry_type) = 'SMS' THEN 'SMS'::communication_channel ELSE 'EMAIL'::communication_channel END,
            CASE WHEN upper(cne.entry_type) = 'SMS' THEN 'CLIENT_NOTE_SMS' ELSE 'CLIENT_NOTE_EMAIL' END,
            'OPERATIONAL',
            CASE
                WHEN a.id IS NULL THEN 'SYSTEM'::communication_sender_category
                WHEN a.role = 'PROF' THEN 'PROFESSOR'::communication_sender_category
                ELSE 'OTHER_USER'::communication_sender_category
            END,
            cne.author_user_id,
            CASE
                WHEN a.id IS NULL THEN 'Systeme'
                ELSE COALESCE(NULLIF(trim(a.first_name || ' ' || a.last_name), ''), a.email, 'Utilisateur')
            END,
            cne.user_id,
            'client:' || cne.user_id::text,
            CASE WHEN upper(cne.entry_type) = 'SMS' THEN 'Operation SMS' ELSE 'Operation email' END,
            COALESCE(cne.message, ''),
            'TEXT'::message_format,
            CASE WHEN upper(cne.entry_type) = 'SMS' THEN 'UNKNOWN'::communication_delivery_status ELSE 'SENT'::communication_delivery_status END,
            'LEGACY',
            COALESCE(cne.created_at, now()),
            COALESCE(cne.created_at, now()),
            now()
        FROM client_note_entries cne
        LEFT JOIN users a ON a.id = cne.author_user_id
        WHERE upper(cne.entry_type) IN ('EMAIL', 'SMS')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_communication_logs_provider_message_id", table_name="communication_logs")
    op.drop_index("ix_communication_logs_professor", table_name="communication_logs")
    op.drop_index("ix_communication_logs_type", table_name="communication_logs")
    op.drop_index("ix_communication_logs_channel_occurred", table_name="communication_logs")
    op.drop_index("ix_communication_logs_occurred_at", table_name="communication_logs")
    op.drop_table("communication_logs")

    communication_delivery_status = postgresql.ENUM(
        "DELIVERED",
        "SENT",
        "FAILED",
        "PENDING",
        "SKIPPED",
        "UNKNOWN",
        name="communication_delivery_status",
    )
    communication_delivery_status.drop(op.get_bind(), checkfirst=True)

    communication_sender_category = postgresql.ENUM(
        "PROFESSOR",
        "SYSTEM",
        "OTHER_USER",
        name="communication_sender_category",
    )
    communication_sender_category.drop(op.get_bind(), checkfirst=True)

    communication_channel = postgresql.ENUM(
        "EMAIL",
        "SMS",
        name="communication_channel",
    )
    communication_channel.drop(op.get_bind(), checkfirst=True)
