from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import date, time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import false, func, or_, select

from app.api.routes.clients import _active_formula_options_for_course_type, _session_purchase_catalog
from app.db.session import SessionLocal
from app.api.routes.admin import BOOKING_STATUSES_ACTIVE
from app.api.routes.admin_clients import _parse_invoice_range_note_entry
from app.models.catalog import Booking, CourseSession, CourseType, CreditType, Location, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.plan import Plan, PlanCreditGrant, PlanEntitlement, PlanKind
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.services.session_audience import resolve_session_booking_scopes

SCRIPT_PREFIX = "PROD_STUDIO_FORMULA_INSPECT"


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def main() -> None:
    with SessionLocal() as db:
        studio_course_types = db.execute(
            select(
                CourseType.id,
                CourseType.name,
                CourseType.service_code,
                CourseType.mode,
                CourseType.credit_type_id,
                CreditType.code,
                CreditType.name,
            )
            .join(CreditType, CreditType.id == CourseType.credit_type_id, isouter=True)
            .where(func.lower(CourseType.name).like("%studio%"))
            .order_by(CourseType.name.asc())
        ).all()

        if not studio_course_types:
            _print("no studio course types found")
            return

        _print(f"studio_course_types={len(studio_course_types)}")
        for row in studio_course_types:
            course_type_id, name, service_code, course_type_mode, credit_type_id, credit_code, credit_name = row
            _print(
                "course_type="
                f"{course_type_id}|name={name}|service_code={service_code or '-'}|"
                f"credit_type_id={credit_type_id or '-'}|credit_type_code={credit_code or '-'}|credit_type_name={credit_name or '-'}"
            )

            exact_public_plans = db.execute(
                select(
                    Plan.id,
                    Plan.code,
                    Plan.name,
                    Plan.kind,
                    Plan.active,
                    Plan.is_private,
                )
                .select_from(Plan)
                .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id)
                .where(
                    PlanEntitlement.course_type_id == course_type_id,
                    Plan.active.is_(True),
                    Plan.is_private.is_(False),
                )
                .order_by(Plan.name.asc())
            ).all()
            _print(f"exact_public_plans_for_{name}={len(exact_public_plans)}")
            for plan_id, plan_code, plan_name, kind, active, is_private in exact_public_plans:
                _print(
                    "exact_public_plan="
                    f"{plan_id}|code={plan_code}|name={plan_name}|kind={getattr(kind, 'value', kind)}|"
                    f"active={active}|private={is_private}"
                )

            entitlement_rows = db.execute(
                select(
                    Plan.id,
                    Plan.code,
                    Plan.name,
                    Plan.kind,
                    Plan.active,
                    Plan.is_private,
                    Plan.options_json,
                    PlanEntitlement.course_type_id,
                    PlanCreditGrant.credit_type_id,
                    PlanCreditGrant.credits_count,
                )
                .select_from(Plan)
                .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id, isouter=True)
                .join(PlanCreditGrant, PlanCreditGrant.plan_id == Plan.id, isouter=True)
                .where(
                    or_(
                        PlanEntitlement.course_type_id == course_type_id,
                        PlanCreditGrant.credit_type_id == credit_type_id if credit_type_id is not None else false(),
                        func.lower(Plan.name).like("%studio%"),
                        func.lower(Plan.code).like("%studio%"),
                    )
                )
                .order_by(Plan.name.asc())
            ).all()
            _print(f"matching_plan_rows_for_{name}={len(entitlement_rows)}")
            for prow in entitlement_rows:
                (
                    plan_id,
                    plan_code,
                    plan_name,
                    kind,
                    active,
                    is_private,
                    options_json,
                    entitlement_course_type_id,
                    grant_credit_type_id,
                    grant_credits_count,
                ) = prow
                _print(
                    "plan_row="
                    f"{plan_id}|code={plan_code}|name={plan_name}|kind={getattr(kind, 'value', kind)}|"
                    f"active={active}|private={is_private}|options={options_json}|"
                    f"entitlement_course_type_id={entitlement_course_type_id or '-'}|"
                    f"grant_credit_type_id={grant_credit_type_id or '-'}|grant_credits_count={grant_credits_count or 0}"
                )

            formula_options = _active_formula_options_for_course_type(
                db,
                course_type_id=course_type_id,
                course_type_name=name,
                course_type_service_code=service_code,
                course_type_mode=course_type_mode,
                credit_type_id=credit_type_id,
                allowed_plan_kinds={PlanKind.PACK, PlanKind.SUBSCRIPTION, PlanKind.FORFAIT},
            )
            _print(
                f"formula_options_for_{name}="
                + (
                    ",".join(
                        f"{option.formula_code}:{option.name}:{getattr(option.formula_type, 'value', option.formula_type)}"
                        for option in formula_options
                    )
                    or "-"
                )
            )

        now = datetime.now(timezone.utc)
        upcoming_sessions = db.execute(
            select(CourseSession, CourseType, Location)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                func.lower(CourseType.name).like("%studio%"),
                CourseSession.start_at_utc >= now - timedelta(days=3),
                CourseSession.start_at_utc <= now + timedelta(days=30),
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()
        _print(f"upcoming_studio_sessions={len(upcoming_sessions)}")
        for session_obj, course_type, location in upcoming_sessions:
            formula_options, direct_payment_amount, direct_payment_currency, session_booking_scopes = _session_purchase_catalog(
                db,
                session_obj=session_obj,
                course_type=course_type,
            )
            _print(
                "session="
                f"{session_obj.id}|start_at_utc={session_obj.start_at_utc.isoformat()}|location={location.name}|"
                f"course_type={course_type.name}|course_type_id={course_type.id}|"
                f"credit_type_id={course_type.credit_type_id or '-'}|status={getattr(session_obj.status, 'value', session_obj.status)}|"
                f"price={session_obj.external_booking_price_ttc or '-'} EUR|"
                f"booking_scopes={','.join(scope.value for scope in resolve_session_booking_scopes(session_obj, allows_student_bookings=bool(course_type.allows_student_bookings)))}|"
                f"catalog_scopes={','.join(scope.value for scope in session_booking_scopes)}|"
                f"catalog_direct_payment={direct_payment_amount or '-'} {direct_payment_currency or '-'}|"
                f"catalog_formulas={(','.join(option.formula_code for option in formula_options) or '-')}"
            )


def diagnose_legacy_friday_series() -> None:
    with SessionLocal() as db:
        booking_rows = db.execute(
            select(Booking, CourseSession)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc >= datetime(2026, 9, 1, tzinfo=timezone.utc),
                CourseSession.start_at_utc < datetime(2027, 7, 1, tzinfo=timezone.utc),
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()
        grouped = defaultdict(list)
        for booking, session_obj in booking_rows:
            local_start = session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))
            if local_start.weekday() != 4:
                continue
            grouped[(booking.user_id, session_obj.course_type_id, session_obj.location_id, local_start.time())].append(
                (booking, session_obj, local_start)
            )
        candidates = []
        for (student_id, course_type_id, location_id, local_time), rows in grouped.items():
            dates = {row[2].date() for row in rows}
            if len(rows) < 15 or max(dates) > date(2027, 6, 18):
                continue
            booking_ids = {row[0].id for row in rows}
            invoice_lines = list(
                db.scalars(
                    select(ClientInvoiceLine).where(
                        ClientInvoiceLine.source == "BOOKING",
                        ClientInvoiceLine.source_payment_id.in_(booking_ids),
                    )
                ).all()
            )
            candidates.append(
                {
                    "student_id": str(student_id),
                    "course_type_id": str(course_type_id),
                    "location_id": str(location_id),
                    "time": local_time.strftime("%H:%M"),
                    "booking_count": len(rows),
                    "first": min(dates).isoformat(),
                    "last": max(dates).isoformat(),
                    "booking_amounts": sorted(
                        {str(Decimal(row[0].total_incl_vat_snapshot or 0).quantize(Decimal("0.01"))) for row in rows}
                    ),
                    "invoice_line_count": len(invoice_lines),
                    "invoice_amounts": sorted(
                        {str(Decimal(line.total_incl_vat or 0).quantize(Decimal("0.01"))) for line in invoice_lines}
                    ),
                }
            )
        print({"legacy_friday_candidates": candidates})

        target_student_id = UUID("ed14d382-d354-4d03-a05e-b6c7cc51f446")
        target_rows = [row for row in booking_rows if row[0].user_id == target_student_id]
        target_groups = defaultdict(list)
        for booking, session_obj in target_rows:
            local_start = session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone or "Europe/Paris"))
            target_groups[
                (session_obj.course_type_id, session_obj.location_id, local_start.weekday(), local_start.time())
            ].append((booking, session_obj, local_start))
        print(
            {
                "target_groups": [
                    {
                        "course_type_id": str(key[0]),
                        "location_id": str(key[1]),
                        "weekday": key[2],
                        "time": key[3].strftime("%H:%M"),
                        "count": len(rows),
                        "dates": [row[2].date().isoformat() for row in rows],
                        "amounts": sorted({str(Decimal(row[0].total_incl_vat_snapshot or 0)) for row in rows}),
                    }
                    for key, rows in target_groups.items()
                ]
            }
        )
        target_booking_ids = {row[0].id for row in target_rows}
        target_invoice_lines = list(
            db.scalars(
                select(ClientInvoiceLine).where(
                    ClientInvoiceLine.source == "BOOKING",
                    ClientInvoiceLine.source_payment_id.in_(target_booking_ids),
                )
            ).all()
        )
        note_ids = {line.note_id for line in target_invoice_lines}
        notes = {
            note.id: note for note in db.scalars(select(ClientNoteEntry).where(ClientNoteEntry.id.in_(note_ids))).all()
        }
        all_note_lines = list(
            db.scalars(select(ClientInvoiceLine).where(ClientInvoiceLine.note_id.in_(note_ids))).all()
        )
        print(
            {
                "target_invoices": [
                    {
                        "invoice_number": str(
                            (_parse_invoice_range_note_entry(notes[note_id]) or {}).get("invoice_number") or ""
                        ),
                        "invoice_status": str(
                            (_parse_invoice_range_note_entry(notes[note_id]) or {}).get("invoice_status") or ""
                        ),
                        "total_ttc": str(
                            sum(
                                (Decimal(line.total_incl_vat or 0) for line in all_note_lines if line.note_id == note_id),
                                Decimal("0"),
                            )
                        ),
                        "target_booking_lines": sum(1 for line in target_invoice_lines if line.note_id == note_id),
                        "target_booking_total": str(
                            sum(
                                (Decimal(line.total_incl_vat or 0) for line in target_invoice_lines if line.note_id == note_id),
                                Decimal("0"),
                            )
                        ),
                    }
                    for note_id in note_ids
                ]
            }
        )
        quote_rows = db.execute(
            select(Quote, QuoteAcceptanceFollowup)
            .join(QuoteAcceptanceFollowup, QuoteAcceptanceFollowup.quote_id == Quote.id)
            .where(Quote.school_year_label == "2026-2027")
        ).all()
        target_quotes = []
        for quote, followup in quote_rows:
            payload = followup.payload if isinstance(followup.payload, dict) else {}
            execution = payload.get("quote_to_enrollment_execution")
            execution = execution if isinstance(execution, dict) else {}
            created_ids = {str(value) for value in execution.get("created_booking_ids") or []}
            if not created_ids.intersection({str(value) for value in target_booking_ids}):
                continue
            lines = list(db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id)).all())
            target_quotes.append(
                {
                    "quote_number": quote.quote_number,
                    "status": str(quote.status),
                    "total_ttc": str(quote.total_ttc),
                    "lines": [
                        {
                            "activity_id": str(line.activity_id) if line.activity_id else None,
                            "quantity": str(line.quantity),
                            "unit_ttc": str(line.unit_price_ttc),
                            "amount_ttc": str(line.amount_ttc),
                        }
                        for line in lines
                    ],
                }
            )
        print({"target_quotes": target_quotes})


if __name__ == "__main__":
    main()
    diagnose_legacy_friday_series()
    from scripts.inspect_prod_diane_friday_series import main as inspect_diane_friday_series

    inspect_diane_friday_series()
