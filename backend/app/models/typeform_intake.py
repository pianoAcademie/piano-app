from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TypeformFormConfig(Base):
    __tablename__ = "typeform_form_configs"
    __table_args__ = (
        UniqueConstraint("typeform_form_id", name="uq_typeform_form_configs_typeform_form_id"),
        UniqueConstraint("source_code", name="uq_typeform_form_configs_source_code"),
        Index("ix_typeform_form_configs_location_segment", "location_code", "audience_segment"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    typeform_form_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_code: Mapped[str] = mapped_column(String(120), nullable=False)
    location_code: Mapped[str] = mapped_column(String(80), nullable=False)
    school_year_label: Mapped[str] = mapped_column(String(80), nullable=False)
    audience_segment: Mapped[str] = mapped_column(String(40), nullable=False)
    default_quote_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    default_quote_type_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quote_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_pricing_catalog_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pricing_catalogs.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_payment_plan_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payment_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_legal_entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("legal_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_language: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'fr'"))
    configuration_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class TypeformIntake(Base):
    __tablename__ = "typeform_intakes"
    __table_args__ = (
        UniqueConstraint("source_form_id", "source_response_id", name="uq_typeform_intakes_source_response"),
        Index("ix_typeform_intakes_status", "intake_status"),
        Index("ix_typeform_intakes_form_config_id", "form_config_id"),
        Index("ix_typeform_intakes_related_quote_id", "related_quote_id"),
        Index("ix_typeform_intakes_received_at", "received_at"),
        Index("ix_typeform_intakes_local_confirmation_status", "local_confirmation_status"),
        Index("ix_typeform_intakes_local_confirmation_assignee", "local_confirmation_assignee_professor_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    form_config_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("typeform_form_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_form_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_response_id: Mapped[str] = mapped_column(String(160), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    normalized_payload_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    simplified_response_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    resolution_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    warnings_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    blocking_reasons_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    intake_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'NEW'"))
    detected_location: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detected_segment: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detected_school_year: Mapped[str | None] = mapped_column(String(80), nullable=True)
    admin_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
    local_confirmation_status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default=text("'NOT_REQUIRED'")
    )
    local_confirmation_assignee_professor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="SET NULL"),
        nullable=True,
    )
    local_confirmation_assignee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    local_confirmation_session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("course_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    local_confirmation_product_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("catalog_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    local_confirmation_schedule_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_confirmation_partition_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_confirmation_partition_not_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    local_confirmation_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_confirmation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    local_confirmation_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    local_confirmation_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    local_confirmation_confirmed_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    local_confirmation_confirmed_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
