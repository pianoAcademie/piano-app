from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class ExternalContentProvider(str, enum.Enum):
    WORDPRESS_LEARNDASH = "WORDPRESS_LEARNDASH"


class ExternalContentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ContentAccessRule(str, enum.Enum):
    ACTIVE_ENROLLMENT = "ACTIVE_ENROLLMENT"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class ExternalContentCourse(Base):
    __tablename__ = "external_content_courses"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_external_content_courses_provider_external_id"),
        Index("ix_external_content_courses_provider", "provider"),
        Index("ix_external_content_courses_status", "status"),
        Index("ix_external_content_courses_level_code", "level_code"),
        Index("ix_external_content_courses_slug", "slug"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    provider: Mapped[ExternalContentProvider] = mapped_column(
        Enum(
            ExternalContentProvider,
            name="external_content_provider",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        server_default=text("'WORDPRESS_LEARNDASH'"),
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    level_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[ExternalContentStatus] = mapped_column(
        Enum(
            ExternalContentStatus,
            name="external_content_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        server_default=text("'PUBLISHED'"),
    )
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ExternalContentSection(Base):
    __tablename__ = "external_content_sections"
    __table_args__ = (
        UniqueConstraint("course_id", "external_id", name="uq_external_content_sections_course_external_id"),
        Index("ix_external_content_sections_course_id", "course_id"),
        Index("ix_external_content_sections_position", "course_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    course_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("external_content_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ExternalContentLesson(Base):
    __tablename__ = "external_content_lessons"
    __table_args__ = (
        UniqueConstraint("course_id", "external_id", name="uq_external_content_lessons_course_external_id"),
        Index("ix_external_content_lessons_course_id", "course_id"),
        Index("ix_external_content_lessons_section_id", "section_id"),
        Index("ix_external_content_lessons_position", "course_id", "position"),
        Index("ix_external_content_lessons_slug", "slug"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    course_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("external_content_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("external_content_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ExternalContentStatus] = mapped_column(
        Enum(
            ExternalContentStatus,
            name="external_content_lesson_status",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        server_default=text("'PUBLISHED'"),
    )
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class CourseTypeContentMapping(Base):
    __tablename__ = "course_type_content_mappings"
    __table_args__ = (
        UniqueConstraint("course_type_id", "content_course_id", name="uq_course_type_content_mappings_pair"),
        Index("ix_course_type_content_mappings_course_type_id", "course_type_id"),
        Index("ix_course_type_content_mappings_content_course_id", "content_course_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    course_type_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_course_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("external_content_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_rule: Mapped[ContentAccessRule] = mapped_column(
        Enum(
            ContentAccessRule,
            name="content_access_rule",
            native_enum=False,
            values_callable=_enum_values,
            validate_strings=True,
        ),
        nullable=False,
        server_default=text("'ACTIVE_ENROLLMENT'"),
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
