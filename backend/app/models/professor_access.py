from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProfessorPermission(Base):
    __tablename__ = "professor_permissions"

    professor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professors.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    can_view_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_clients: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_export_clients: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_create_clients: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_message_clients: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_client_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_create_subscriptions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_close_subscriptions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_edit_subscriptions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_downgrade_subscriptions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_cancel_subscriptions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_edit_payments: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_refund_payments: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_cancel_payments: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_manage_mobile_news: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_access_cash_menu: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_view_planning: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    can_view_all_school_sessions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_edit_planning: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_force_booking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_view_admin_dashboard: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_admin_reservations: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_access_collaborators: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_planning_simulation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    planning_simulation_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    can_manage_check_deposits: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    check_deposits_location_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    can_view_intakes: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_quotes: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_configure_app: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_list_payments: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_manage_events: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_sportigo_info: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_take_attendance: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    can_record_payments_with_attendance: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_edit_own_sessions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_pay_details: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_manage_mileage_log: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_view_other_teachers_contacts: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_manage_other_teachers_students_and_sessions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_other_teachers_sessions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_view_student_parent_addresses_phones: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_student_parent_emails: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_view_student_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    can_manage_invoices_and_accounts: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_manage_expenses_and_other_income: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_manage_shared_online_resources: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_manage_website_and_news: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    can_create_and_view_reports: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

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
