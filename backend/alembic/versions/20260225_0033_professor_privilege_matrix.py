"""add professor privilege matrix fields

Revision ID: 20260225_0033
Revises: 20260225_0032
Create Date: 2026-02-25 09:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260225_0033"
down_revision: Union[str, None] = "20260225_0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professor_permissions",
        sa.Column("can_take_attendance", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_record_payments_with_attendance", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_edit_own_sessions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_pay_details", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_manage_mileage_log", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_other_teachers_contacts", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column(
            "can_manage_other_teachers_students_and_sessions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_other_teachers_sessions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_student_parent_addresses_phones", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_student_parent_emails", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_view_student_attachments", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_manage_invoices_and_accounts", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_manage_expenses_and_other_income", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_manage_shared_online_resources", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_manage_website_and_news", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "professor_permissions",
        sa.Column("can_create_and_view_reports", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("professor_permissions", "can_create_and_view_reports")
    op.drop_column("professor_permissions", "can_manage_website_and_news")
    op.drop_column("professor_permissions", "can_manage_shared_online_resources")
    op.drop_column("professor_permissions", "can_manage_expenses_and_other_income")
    op.drop_column("professor_permissions", "can_manage_invoices_and_accounts")
    op.drop_column("professor_permissions", "can_view_student_attachments")
    op.drop_column("professor_permissions", "can_view_student_parent_emails")
    op.drop_column("professor_permissions", "can_view_student_parent_addresses_phones")
    op.drop_column("professor_permissions", "can_view_other_teachers_sessions")
    op.drop_column("professor_permissions", "can_manage_other_teachers_students_and_sessions")
    op.drop_column("professor_permissions", "can_view_other_teachers_contacts")
    op.drop_column("professor_permissions", "can_manage_mileage_log")
    op.drop_column("professor_permissions", "can_view_pay_details")
    op.drop_column("professor_permissions", "can_edit_own_sessions")
    op.drop_column("professor_permissions", "can_record_payments_with_attendance")
    op.drop_column("professor_permissions", "can_take_attendance")
