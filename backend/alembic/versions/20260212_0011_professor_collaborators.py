"""Add professor collaborator settings and permissions

Revision ID: 20260212_0011
Revises: 20260212_0010
Create Date: 2026-02-12 17:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260212_0011"
down_revision: Union[str, None] = "20260212_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("professors", sa.Column("zoom_link", sa.Text(), nullable=True))
    op.add_column("professors", sa.Column("spoken_languages", sa.Text(), nullable=True))
    op.add_column(
        "professors",
        sa.Column("is_coach", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "professors",
        sa.Column("last_activation_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "professors",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.execute("UPDATE professors SET updated_at = COALESCE(created_at, now())")

    op.create_table(
        "professor_permissions",
        sa.Column(
            "professor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professors.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("can_view_dashboard", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_view_clients", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_export_clients", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_create_clients", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_message_clients", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_view_client_reminders", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_create_subscriptions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_close_subscriptions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_edit_subscriptions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_downgrade_subscriptions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_cancel_subscriptions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_edit_payments", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_refund_payments", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_cancel_payments", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_manage_mobile_news", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_access_cash_menu", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_view_planning", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("can_edit_planning", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_force_booking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_view_admin_dashboard", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_view_admin_reservations", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_access_collaborators", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_configure_app", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_list_payments", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_manage_events", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_view_sportigo_info", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.execute(
        """
        INSERT INTO professor_permissions (
            professor_id,
            can_view_planning,
            can_edit_planning,
            can_force_booking
        )
        SELECT p.id, true, true, true
        FROM professors p
        WHERE NOT EXISTS (
            SELECT 1
            FROM professor_permissions pp
            WHERE pp.professor_id = p.id
        )
        """
    )


def downgrade() -> None:
    op.drop_table("professor_permissions")

    op.drop_column("professors", "updated_at")
    op.drop_column("professors", "last_activation_email_sent_at")
    op.drop_column("professors", "is_coach")
    op.drop_column("professors", "spoken_languages")
    op.drop_column("professors", "zoom_link")
