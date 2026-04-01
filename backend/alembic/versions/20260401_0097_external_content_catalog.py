"""external content catalog

Revision ID: 20260401_0097
Revises: 20260401_0096
Create Date: 2026-04-01 10:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260401_0097"
down_revision: Union[str, None] = "20260401_0096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


external_content_provider_enum = sa.Enum(
    "WORDPRESS_LEARNDASH",
    name="external_content_provider",
    native_enum=False,
)
external_content_status_enum = sa.Enum(
    "DRAFT",
    "PUBLISHED",
    "ARCHIVED",
    name="external_content_status",
    native_enum=False,
)
external_content_lesson_status_enum = sa.Enum(
    "DRAFT",
    "PUBLISHED",
    "ARCHIVED",
    name="external_content_lesson_status",
    native_enum=False,
)
content_access_rule_enum = sa.Enum(
    "ACTIVE_ENROLLMENT",
    "MANUAL_OVERRIDE",
    name="content_access_rule",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "external_content_courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("provider", external_content_provider_enum, nullable=False, server_default=sa.text("'WORDPRESS_LEARNDASH'")),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("level_code", sa.String(length=80), nullable=True),
        sa.Column("status", external_content_status_enum, nullable=False, server_default=sa.text("'PUBLISHED'")),
        sa.Column("cover_image_url", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_external_content_courses_provider_external_id"),
    )
    op.create_index("ix_external_content_courses_provider", "external_content_courses", ["provider"], unique=False)
    op.create_index("ix_external_content_courses_status", "external_content_courses", ["status"], unique=False)
    op.create_index("ix_external_content_courses_level_code", "external_content_courses", ["level_code"], unique=False)
    op.create_index("ix_external_content_courses_slug", "external_content_courses", ["slug"], unique=False)

    op.create_table(
        "external_content_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["course_id"], ["external_content_courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "external_id", name="uq_external_content_sections_course_external_id"),
    )
    op.create_index("ix_external_content_sections_course_id", "external_content_sections", ["course_id"], unique=False)
    op.create_index("ix_external_content_sections_position", "external_content_sections", ["course_id", "position"], unique=False)

    op.create_table(
        "external_content_lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("resource_url", sa.Text(), nullable=True),
        sa.Column("status", external_content_lesson_status_enum, nullable=False, server_default=sa.text("'PUBLISHED'")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["course_id"], ["external_content_courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["external_content_sections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "external_id", name="uq_external_content_lessons_course_external_id"),
    )
    op.create_index("ix_external_content_lessons_course_id", "external_content_lessons", ["course_id"], unique=False)
    op.create_index("ix_external_content_lessons_section_id", "external_content_lessons", ["section_id"], unique=False)
    op.create_index("ix_external_content_lessons_position", "external_content_lessons", ["course_id", "position"], unique=False)
    op.create_index("ix_external_content_lessons_slug", "external_content_lessons", ["slug"], unique=False)

    op.create_table(
        "course_type_content_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("course_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_rule", content_access_rule_enum, nullable=False, server_default=sa.text("'ACTIVE_ENROLLMENT'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["content_course_id"], ["external_content_courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_type_id"], ["course_types.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_type_id", "content_course_id", name="uq_course_type_content_mappings_pair"),
    )
    op.create_index("ix_course_type_content_mappings_course_type_id", "course_type_content_mappings", ["course_type_id"], unique=False)
    op.create_index("ix_course_type_content_mappings_content_course_id", "course_type_content_mappings", ["content_course_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_course_type_content_mappings_content_course_id", table_name="course_type_content_mappings")
    op.drop_index("ix_course_type_content_mappings_course_type_id", table_name="course_type_content_mappings")
    op.drop_table("course_type_content_mappings")

    op.drop_index("ix_external_content_lessons_slug", table_name="external_content_lessons")
    op.drop_index("ix_external_content_lessons_position", table_name="external_content_lessons")
    op.drop_index("ix_external_content_lessons_section_id", table_name="external_content_lessons")
    op.drop_index("ix_external_content_lessons_course_id", table_name="external_content_lessons")
    op.drop_table("external_content_lessons")

    op.drop_index("ix_external_content_sections_position", table_name="external_content_sections")
    op.drop_index("ix_external_content_sections_course_id", table_name="external_content_sections")
    op.drop_table("external_content_sections")

    op.drop_index("ix_external_content_courses_slug", table_name="external_content_courses")
    op.drop_index("ix_external_content_courses_level_code", table_name="external_content_courses")
    op.drop_index("ix_external_content_courses_status", table_name="external_content_courses")
    op.drop_index("ix_external_content_courses_provider", table_name="external_content_courses")
    op.drop_table("external_content_courses")
