"""add Bar-le-Duc intake local confirmation workflow

Revision ID: 20260804_0174
Revises: 20260804_0173
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260804_0174"
down_revision = "20260804_0173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "typeform_intakes",
        sa.Column(
            "local_confirmation_status",
            sa.String(length=40),
            server_default=sa.text("'NOT_REQUIRED'"),
            nullable=False,
        ),
    )
    op.add_column(
        "typeform_intakes",
        sa.Column("local_confirmation_assignee_professor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("typeform_intakes", sa.Column("local_confirmation_assignee_name", sa.String(length=255), nullable=True))
    op.add_column(
        "typeform_intakes",
        sa.Column("local_confirmation_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "typeform_intakes",
        sa.Column("local_confirmation_product_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("typeform_intakes", sa.Column("local_confirmation_schedule_snapshot", sa.Text(), nullable=True))
    op.add_column("typeform_intakes", sa.Column("local_confirmation_partition_snapshot", sa.Text(), nullable=True))
    op.add_column(
        "typeform_intakes",
        sa.Column("local_confirmation_partition_not_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("typeform_intakes", sa.Column("local_confirmation_comment", sa.Text(), nullable=True))
    op.add_column("typeform_intakes", sa.Column("local_confirmation_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("typeform_intakes", sa.Column("local_confirmation_notified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("typeform_intakes", sa.Column("local_confirmation_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "typeform_intakes",
        sa.Column("local_confirmation_confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("typeform_intakes", sa.Column("local_confirmation_confirmed_by_name", sa.String(length=255), nullable=True))

    op.create_foreign_key(
        "fk_typeform_intakes_local_confirmation_assignee_professor",
        "typeform_intakes",
        "professors",
        ["local_confirmation_assignee_professor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_typeform_intakes_local_confirmation_session",
        "typeform_intakes",
        "course_sessions",
        ["local_confirmation_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_typeform_intakes_local_confirmation_product",
        "typeform_intakes",
        "catalog_products",
        ["local_confirmation_product_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_typeform_intakes_local_confirmation_user",
        "typeform_intakes",
        "users",
        ["local_confirmation_confirmed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_typeform_intakes_local_confirmation_status",
        "typeform_intakes",
        ["local_confirmation_status"],
    )
    op.create_index(
        "ix_typeform_intakes_local_confirmation_assignee",
        "typeform_intakes",
        ["local_confirmation_assignee_professor_id"],
    )

    op.execute(
        """
        UPDATE typeform_form_configs
        SET configuration_json = coalesce(configuration_json, '{}'::jsonb)
            || jsonb_build_object('local_confirmation_professor_email', 'estela.oliviero@piano-academie.com'),
            updated_at = now()
        WHERE lower(replace(coalesce(location_code, ''), '_', '-')) LIKE '%bar%duc%'
        """
    )
    op.execute(
        """
        UPDATE typeform_intakes AS intake
        SET local_confirmation_status = 'PENDING',
            local_confirmation_assignee_professor_id = professor.id,
            local_confirmation_assignee_name = trim(professor.first_name || ' ' || professor.last_name),
            local_confirmation_requested_at = coalesce(intake.received_at, now()),
            updated_at = now()
        FROM professors AS professor
        WHERE lower(professor.email) = 'estela.oliviero@piano-academie.com'
          AND (
            lower(replace(coalesce(intake.detected_location, ''), '_', '-')) LIKE '%bar%duc%'
            OR EXISTS (
              SELECT 1
              FROM typeform_form_configs AS config
              WHERE config.id = intake.form_config_id
                AND lower(replace(coalesce(config.location_code, ''), '_', '-')) LIKE '%bar%duc%'
            )
          )
          AND intake.local_confirmation_status = 'NOT_REQUIRED'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_typeform_intakes_local_confirmation_assignee", table_name="typeform_intakes")
    op.drop_index("ix_typeform_intakes_local_confirmation_status", table_name="typeform_intakes")
    op.drop_constraint("fk_typeform_intakes_local_confirmation_user", "typeform_intakes", type_="foreignkey")
    op.drop_constraint("fk_typeform_intakes_local_confirmation_product", "typeform_intakes", type_="foreignkey")
    op.drop_constraint("fk_typeform_intakes_local_confirmation_session", "typeform_intakes", type_="foreignkey")
    op.drop_constraint("fk_typeform_intakes_local_confirmation_assignee_professor", "typeform_intakes", type_="foreignkey")
    for column in (
        "local_confirmation_confirmed_by_name",
        "local_confirmation_confirmed_by_user_id",
        "local_confirmation_confirmed_at",
        "local_confirmation_notified_at",
        "local_confirmation_requested_at",
        "local_confirmation_comment",
        "local_confirmation_partition_not_required",
        "local_confirmation_partition_snapshot",
        "local_confirmation_schedule_snapshot",
        "local_confirmation_product_id",
        "local_confirmation_session_id",
        "local_confirmation_assignee_name",
        "local_confirmation_assignee_professor_id",
        "local_confirmation_status",
    ):
        op.drop_column("typeform_intakes", column)
