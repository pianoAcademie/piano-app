from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.professor_access import ProfessorPermission

PERMISSION_FIELDS: tuple[str, ...] = (
    "can_view_dashboard",
    "can_view_clients",
    "can_export_clients",
    "can_create_clients",
    "can_message_clients",
    "can_view_client_reminders",
    "can_create_subscriptions",
    "can_close_subscriptions",
    "can_edit_subscriptions",
    "can_downgrade_subscriptions",
    "can_cancel_subscriptions",
    "can_edit_payments",
    "can_refund_payments",
    "can_cancel_payments",
    "can_manage_mobile_news",
    "can_access_cash_menu",
    "can_view_planning",
    "can_view_all_school_sessions",
    "can_edit_planning",
    "can_force_booking",
    "can_view_admin_dashboard",
    "can_view_admin_reservations",
    "can_access_collaborators",
    "can_view_planning_simulation",
    "can_manage_check_deposits",
    "can_view_intakes",
    "can_view_quotes",
    "can_configure_app",
    "can_list_payments",
    "can_manage_events",
    "can_view_sportigo_info",
    "can_take_attendance",
    "can_record_payments_with_attendance",
    "can_edit_own_sessions",
    "can_view_pay_details",
    "can_manage_mileage_log",
    "can_view_other_teachers_contacts",
    "can_manage_other_teachers_students_and_sessions",
    "can_view_other_teachers_sessions",
    "can_view_student_parent_addresses_phones",
    "can_view_student_parent_emails",
    "can_view_student_attachments",
    "can_manage_invoices_and_accounts",
    "can_manage_expenses_and_other_income",
    "can_manage_shared_online_resources",
    "can_manage_website_and_news",
    "can_create_and_view_reports",
)

DEFAULT_PROFESSOR_PERMISSIONS: dict[str, bool] = {
    "can_view_dashboard": False,
    "can_view_clients": False,
    "can_export_clients": False,
    "can_create_clients": False,
    "can_message_clients": False,
    "can_view_client_reminders": False,
    "can_create_subscriptions": False,
    "can_close_subscriptions": False,
    "can_edit_subscriptions": False,
    "can_downgrade_subscriptions": False,
    "can_cancel_subscriptions": False,
    "can_edit_payments": False,
    "can_refund_payments": False,
    "can_cancel_payments": False,
    "can_manage_mobile_news": False,
    "can_access_cash_menu": False,
    "can_view_planning": True,
    "can_view_all_school_sessions": False,
    "can_edit_planning": False,
    "can_force_booking": False,
    "can_view_admin_dashboard": False,
    "can_view_admin_reservations": False,
    "can_access_collaborators": False,
    "can_view_planning_simulation": False,
    "can_manage_check_deposits": False,
    "can_view_intakes": False,
    "can_view_quotes": False,
    "can_configure_app": False,
    "can_list_payments": False,
    "can_manage_events": False,
    "can_view_sportigo_info": False,
    "can_take_attendance": True,
    "can_record_payments_with_attendance": False,
    "can_edit_own_sessions": False,
    "can_view_pay_details": False,
    "can_manage_mileage_log": False,
    "can_view_other_teachers_contacts": False,
    "can_manage_other_teachers_students_and_sessions": False,
    "can_view_other_teachers_sessions": False,
    "can_view_student_parent_addresses_phones": False,
    "can_view_student_parent_emails": False,
    "can_view_student_attachments": False,
    "can_manage_invoices_and_accounts": False,
    "can_manage_expenses_and_other_income": False,
    "can_manage_shared_online_resources": False,
    "can_manage_website_and_news": False,
    "can_create_and_view_reports": False,
}

LEGACY_FALLBACK_PERMISSIONS: dict[str, bool] = {
    **DEFAULT_PROFESSOR_PERMISSIONS,
    "can_edit_planning": True,
    "can_take_attendance": True,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def permissions_dict(row: ProfessorPermission | None, *, legacy_if_missing: bool = False) -> dict[str, Any]:
    if row is None:
        if legacy_if_missing:
            payload = dict(LEGACY_FALLBACK_PERMISSIONS)
        else:
            payload = dict(DEFAULT_PROFESSOR_PERMISSIONS)
        payload["planning_simulation_location_id"] = None
        payload["check_deposits_location_id"] = None
        return payload

    payload = {field: bool(getattr(row, field)) for field in PERMISSION_FIELDS}
    payload["planning_simulation_location_id"] = row.planning_simulation_location_id
    payload["check_deposits_location_id"] = row.check_deposits_location_id
    return payload


def ensure_permissions_row(
    db: Session,
    *,
    professor_id: UUID,
    defaults: dict[str, bool] | None = None,
    lock: bool = False,
) -> ProfessorPermission:
    stmt = select(ProfessorPermission).where(ProfessorPermission.professor_id == professor_id)
    if lock:
        stmt = stmt.with_for_update()

    row = db.scalar(stmt)
    if row is not None:
        return row

    seed = dict(DEFAULT_PROFESSOR_PERMISSIONS)
    if defaults:
        for key, value in defaults.items():
            if key in seed:
                seed[key] = bool(value)

    row = ProfessorPermission(
        professor_id=professor_id,
        **seed,
        updated_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row
