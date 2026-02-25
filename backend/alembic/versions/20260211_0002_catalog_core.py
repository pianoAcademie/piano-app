"""Add catalogue core tables

Revision ID: 20260211_0002
Revises: 20260211_0001
Create Date: 2026-02-11 13:50:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260211_0002"
down_revision: Union[str, None] = "20260211_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    delivery_mode = postgresql.ENUM("ONLINE", "ONSITE", "ANY", name="delivery_mode")
    delivery_mode.create(op.get_bind(), checkfirst=True)

    session_status = postgresql.ENUM("SCHEDULED", "CANCELLED", "COMPLETED", name="session_status")
    session_status.create(op.get_bind(), checkfirst=True)

    booking_status = postgresql.ENUM("BOOKED", "CANCELLED", "ATTENDED", "NO_SHOW", name="booking_status")
    booking_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "professors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("payout_currency", sa.String(length=3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_professors_email", "professors", ["email"], unique=True)

    op.create_table(
        "locations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address_line", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "(is_online = true and address_line is null and city is null and country_code is null) "
            "or (is_online = false and address_line is not null and city is not null and country_code is not null)",
            name="ck_locations_online_address",
        ),
    )
    op.create_index("ix_locations_code", "locations", ["code"], unique=True)

    op.create_table(
        "course_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("service_code", sa.String(length=80), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "mode",
            postgresql.ENUM("ONLINE", "ONSITE", "ANY", name="delivery_mode", create_type=False),
            nullable=False,
        ),
        sa.Column("default_capacity", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("duration_minutes > 0", name="ck_course_types_duration_positive"),
        sa.CheckConstraint("default_capacity > 0", name="ck_course_types_capacity_positive"),
    )
    op.create_index("ix_course_types_code", "course_types", ["code"], unique=True)

    op.create_table(
        "course_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("course_types.id"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("professors.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity_max", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("SCHEDULED", "CANCELLED", "COMPLETED", name="session_status", create_type=False),
            nullable=False,
            server_default=sa.text("'SCHEDULED'::session_status"),
        ),
        sa.Column("auto_cancel_deadline_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("zoom_link", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("end_at_utc > start_at_utc", name="ck_course_sessions_end_after_start"),
        sa.CheckConstraint("capacity_max > 0", name="ck_course_sessions_capacity_positive"),
    )
    op.create_index(
        "idx_course_sessions_calendar",
        "course_sessions",
        ["start_at_utc", "status", "location_id", "course_type_id"],
        unique=False,
    )

    op.create_table(
        "bookings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("BOOKED", "CANCELLED", "ATTENDED", "NO_SHOW", name="booking_status", create_type=False),
            nullable=False,
            server_default=sa.text("'BOOKED'::booking_status"),
        ),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("session_id", "user_id", name="uq_bookings_session_user"),
    )
    op.create_index("idx_bookings_session_status", "bookings", ["session_id", "status"], unique=False)

    op.execute(
        """
        INSERT INTO locations (code, name, address_line, city, country_code, is_online, timezone)
        VALUES
            ('ASSAS', 'Rue d Assas', 'Rue d Assas', 'Paris', 'FR', false, 'Europe/Paris'),
            ('RICHELIEU', 'Rue de Richelieu', 'Rue de Richelieu', 'Paris', 'FR', false, 'Europe/Paris'),
            ('POMPE', 'Rue de la Pompe', 'Rue de la Pompe', 'Paris', 'FR', false, 'Europe/Paris'),
            ('SCHEFFER', 'Rue Scheffer', 'Rue Scheffer', 'Paris', 'FR', false, 'Europe/Paris'),
            ('ONLINE', 'Online', null, null, null, true, 'UTC')
        """
    )

    op.execute(
        """
        INSERT INTO course_types (code, name, service_code, duration_minutes, mode, default_capacity)
        VALUES
            ('PIANO_GROUP_ONSITE_1H', 'Cours de piano collectif en presentiel (1h)', 'PIANO_CLASS', 60, 'ONSITE', 8),
            ('PIANO_GROUP_ONLINE_1H', 'Cours de piano collectif en ligne (1h)', 'PIANO_CLASS', 60, 'ONLINE', 12),
            ('SOLFEGE_ONLINE_30M', 'Cours de solfege en ligne (30mn)', 'SOLFEGE', 30, 'ONLINE', 15),
            ('STUDIO_REHEARSAL', 'Reservation studio de repetition', 'STUDIO', 60, 'ONSITE', 4)
        """
    )

    op.execute(
        """
        INSERT INTO professors (first_name, last_name, email, payout_currency)
        VALUES ('Demo', 'Professor', 'prof.demo@piano-academie.local', 'EUR')
        """
    )

    op.execute(
        """
        INSERT INTO course_sessions (
            course_type_id,
            location_id,
            professor_id,
            title,
            description,
            start_at_utc,
            end_at_utc,
            capacity_max,
            status,
            auto_cancel_deadline_utc,
            zoom_link
        )
        SELECT
            ct.id,
            l.id,
            p.id,
            'Cours collectif piano presentiel',
            'Session de demonstration en presentiel',
            '2026-03-01 10:00:00+00',
            '2026-03-01 11:00:00+00',
            8,
            'SCHEDULED',
            '2026-03-01 04:00:00+00',
            NULL
        FROM course_types ct
        JOIN locations l ON l.code = 'ASSAS'
        JOIN professors p ON p.email = 'prof.demo@piano-academie.local'
        WHERE ct.code = 'PIANO_GROUP_ONSITE_1H'
        LIMIT 1
        """
    )

    op.execute(
        """
        INSERT INTO course_sessions (
            course_type_id,
            location_id,
            professor_id,
            title,
            description,
            start_at_utc,
            end_at_utc,
            capacity_max,
            status,
            auto_cancel_deadline_utc,
            zoom_link
        )
        SELECT
            ct.id,
            l.id,
            p.id,
            'Cours collectif piano en ligne',
            'Session de demonstration en ligne',
            '2026-03-02 18:00:00+00',
            '2026-03-02 19:00:00+00',
            12,
            'SCHEDULED',
            '2026-03-02 12:00:00+00',
            'https://zoom.us/j/demo-piano-session'
        FROM course_types ct
        JOIN locations l ON l.code = 'ONLINE'
        JOIN professors p ON p.email = 'prof.demo@piano-academie.local'
        WHERE ct.code = 'PIANO_GROUP_ONLINE_1H'
        LIMIT 1
        """
    )


def downgrade() -> None:
    op.drop_index("idx_bookings_session_status", table_name="bookings")
    op.drop_table("bookings")

    op.drop_index("idx_course_sessions_calendar", table_name="course_sessions")
    op.drop_table("course_sessions")

    op.drop_index("ix_course_types_code", table_name="course_types")
    op.drop_table("course_types")

    op.drop_index("ix_locations_code", table_name="locations")
    op.drop_table("locations")

    op.drop_index("ix_professors_email", table_name="professors")
    op.drop_table("professors")

    booking_status = postgresql.ENUM("BOOKED", "CANCELLED", "ATTENDED", "NO_SHOW", name="booking_status")
    booking_status.drop(op.get_bind(), checkfirst=True)

    session_status = postgresql.ENUM("SCHEDULED", "CANCELLED", "COMPLETED", name="session_status")
    session_status.drop(op.get_bind(), checkfirst=True)

    delivery_mode = postgresql.ENUM("ONLINE", "ONSITE", "ANY", name="delivery_mode")
    delivery_mode.drop(op.get_bind(), checkfirst=True)
