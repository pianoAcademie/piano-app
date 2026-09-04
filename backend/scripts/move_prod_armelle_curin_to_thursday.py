from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import (
    BOOKING_STATUSES_ACTIVE,
    BOOKING_STATUSES_COUNTED_AS_RESERVED,
    _bind_moved_contract,
    _checked_move_version,
    _move_planning_reorganization_booking_occurrence,
)
from app.api.routes.admin_clients import create_admin_client_range_invoice
from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, SessionStatus
from app.models.plan import ClientPlanSubscription
from app.models.user import User, UserRole
from app.schemas.admin import AdminRangeInvoiceCreateRequest
from app.services.reminders import ensure_booking_reminder


PREFIX = "PROD_MOVE_ARMELLE_CURIN_THURSDAY_20260904"
STUDENT_ID = UUID("8442aea7-6395-49c7-8150-57a0e1bb29c8")
SOURCE_GROUP_ID = UUID("97e38389-a57f-4e3e-ae73-607cec059e86")
TARGET_GROUP_ID = UUID("3c0f8f87-70d5-4e1d-bc41-74c53859e317")
EXPECTED_SOURCE_COUNT = 31
EXPECTED_TARGET_COUNT = 33
EXPECTED_EXTRA_TOTAL = Decimal("46.80")
UNIT_HT = Decimal("19.50")
VAT_RATE = Decimal("20.00")
UNIT_VAT = Decimal("3.90")
UNIT_TTC = Decimal("23.40")
PARIS = ZoneInfo("Europe/Paris")


def abort(reason: str) -> None:
    raise RuntimeError(f"{PREFIX}|abort|reason={reason}")


def local(session: CourseSession) -> datetime:
    return session.start_at_utc.astimezone(PARIS)


def active_bookings(db):
    return list(db.scalars(select(Booking).join(CourseSession).where(
        Booking.user_id == STUDENT_ID,
        Booking.status.in_(BOOKING_STATUSES_ACTIVE),
        CourseSession.recurrence_group_id == SOURCE_GROUP_ID,
    ).order_by(CourseSession.start_at_utc).with_for_update()).all())


def target_sessions(db):
    return list(db.scalars(select(CourseSession).where(
        CourseSession.recurrence_group_id == TARGET_GROUP_ID,
        CourseSession.status == SessionStatus.SCHEDULED,
    ).order_by(CourseSession.start_at_utc).with_for_update()).all())


def capacity_guard(db, session: CourseSession) -> None:
    reserved = int(db.scalar(select(func.count(Booking.id)).where(
        Booking.session_id == session.id,
        Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED),
    )) or 0)
    if reserved >= session.capacity_max:
        abort(f"target_full_{session.id}_{reserved}_{session.capacity_max}")


def append_contract_session(subscription: ClientPlanSubscription, booking: Booking, session: CourseSession) -> None:
    terms = [dict(term) for term in (subscription.annual_pricing_terms or [])]
    matches = [term for term in terms if term.get("version") == booking.price_book_version_snapshot]
    if len(matches) != 1:
        abort(f"annual_term_match_count_{len(matches)}")
    term = matches[0]
    sid = str(session.id)
    term["session_ids"] = sorted(set(term.get("session_ids", [])) | {sid})
    term["series_ids"] = sorted(set(term.get("series_ids", [])) | {str(TARGET_GROUP_ID)})
    prices = dict(term.get("session_prices", {}))
    prices[sid] = {
        "amount_excl_vat": str(UNIT_HT), "vat_rate": str(VAT_RATE),
        "vat_amount": str(UNIT_VAT), "total_incl_vat": str(UNIT_TTC), "currency": "EUR",
    }
    term["session_prices"] = prices
    subscription.annual_pricing_terms = terms


def clone_extra_booking(template: Booking, session: CourseSession) -> Booking:
    return Booking(
        session_id=session.id, user_id=STUDENT_ID,
        client_plan_subscription_id=template.client_plan_subscription_id,
        manual_credit_type_id=template.manual_credit_type_id,
        status=BookingStatus.BOOKED, booked_at=datetime.now(timezone.utc),
        price_excl_vat_snapshot=UNIT_HT, vat_rate_snapshot=VAT_RATE,
        vat_amount_snapshot=UNIT_VAT, total_incl_vat_snapshot=UNIT_TTC,
        currency_snapshot="EUR", pricing_snapshot_locked=True,
        pricing_channel_snapshot=template.pricing_channel_snapshot,
        pricing_source_snapshot=template.pricing_source_snapshot,
        pricing_unit_snapshot=template.pricing_unit_snapshot,
        price_book_version_snapshot=template.price_book_version_snapshot,
        pricing_breakdown_snapshot=template.pricing_breakdown_snapshot or {},
        pricing_calculated_at=datetime.now(timezone.utc),
        student_note=template.student_note, internal_note=template.internal_note,
        is_trial_course=False, makeup_credit_consumed=False, makeup_override_applied=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        student = db.scalar(select(User).where(User.id == STUDENT_ID).with_for_update())
        if student is None or (student.first_name, student.last_name) != ("Armelle", "CURIN"):
            abort("student_identity_changed")
        source = active_bookings(db)
        targets = target_sessions(db)
        already_target = list(db.scalars(select(Booking).join(CourseSession).where(
            Booking.user_id == STUDENT_ID, Booking.status.in_(BOOKING_STATUSES_ACTIVE),
            CourseSession.recurrence_group_id == TARGET_GROUP_ID,
        )).all())
        if not source and len(already_target) == EXPECTED_TARGET_COUNT:
            invoice_lines = db.execute(select(Booking.id).where(Booking.id.in_([b.id for b in already_target]))).all()
            print(f"{PREFIX}|summary|result=already_moved|bookings={len(invoice_lines)}")
            db.rollback(); return 0
        if len(source) != EXPECTED_SOURCE_COUNT or len(targets) != EXPECTED_TARGET_COUNT or already_target:
            abort(f"unexpected_counts_source_{len(source)}_target_{len(targets)}_already_{len(already_target)}")
        if local(targets[0]).isoformat() != "2026-09-10T17:00:00+02:00":
            abort(f"unexpected_first_target_{local(targets[0]).isoformat()}")
        source_sessions = [db.get(CourseSession, booking.session_id) for booking in source]
        # The Bar-le-Duc calendars are not week-isomorphic: the Monday series has
        # a lesson in the week of 3 May while the Thursday series is closed. The
        # requested annual destination is therefore the ordered set of 33 actual
        # Thursday lessons, not a same-week recurrence projection.
        pairs = list(zip(source, source_sessions, targets[:EXPECTED_SOURCE_COUNT], strict=True))
        _checked_move_version(db, pairs, 0, [], datetime.now(timezone.utc))
        if len(pairs) != EXPECTED_SOURCE_COUNT:
            abort(f"pair_count_{len(pairs)}")
        mapped = {target.id for _, _, target in pairs}
        extras = [session for session in targets if session.id not in mapped]
        if len(extras) != 2:
            abort(f"extra_count_{len(extras)}")
        for session in targets:
            capacity_guard(db, session)
        subscription_ids = {booking.client_plan_subscription_id for booking in source}
        if len(subscription_ids) != 1 or None in subscription_ids:
            abort(f"subscription_count_{subscription_ids}")
        subscription = db.scalar(select(ClientPlanSubscription).where(
            ClientPlanSubscription.id == next(iter(subscription_ids))).with_for_update())
        if subscription is None:
            abort("subscription_missing")
        payer_id = subscription.payer_contact_id or student.id
        actor = db.scalar(select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at).limit(1))
        if actor is None:
            abort("admin_actor_missing")
        print(f"{PREFIX}|audit|source=31|target=33|first=2026-09-10T17:00|extras={','.join(local(s).date().isoformat() for s in extras)}|payer={payer_id}|apply={args.apply}")
        if not args.apply:
            db.rollback(); return 0
        now = datetime.now(timezone.utc)
        for booking, source_session, target in pairs:
            _bind_moved_contract(db, booking, target, "series_future")
            moved, detail = _move_planning_reorganization_booking_occurrence(
                db, booking=booking, source_session=source_session, target_session=target,
                now=now, target_price_snapshot=None, lock_price_snapshot=True,
            )
            if not moved:
                abort(f"move_failed_{detail}")
        created = []
        for session in extras:
            booking = clone_extra_booking(source[0], session)
            db.add(booking); db.flush()
            append_contract_session(subscription, booking, session)
            ensure_booking_reminder(db, booking=booking, session_obj=session, now=now)
            created.append(booking)
        db.commit()

        today = date.today()
        payload = AdminRangeInvoiceCreateRequest(
            issued_date=today, due_date=today, start_date=local(extras[0]).date(), end_date=local(extras[-1]).date(),
            selected_payment_keys=[f"BOOKING:{booking.id}" for booking in created],
            auto_include_previous_balance=False,
            public_note="Facture complémentaire liée au transfert du lundi au jeudi : 32 cours sont prévus le jeudi au lieu de 31 le lundi.",
            private_note="Armelle Curin — transfert annuel Bar-le-Duc vers jeudi 17 h; deux séances supplémentaires; aucun email envoyé automatiquement.",
        )
        invoice = create_admin_client_range_invoice(payer_id, payload, db=db, actor=actor)
        with SessionLocal() as verify:
            final = list(verify.scalars(select(Booking).join(CourseSession).where(
                Booking.user_id == STUDENT_ID, Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                CourseSession.recurrence_group_id == TARGET_GROUP_ID,
            )).all())
            remaining = active_bookings(verify)
            if len(final) != EXPECTED_TARGET_COUNT or remaining:
                abort(f"postcheck_source_{len(remaining)}_target_{len(final)}")
        print(f"{PREFIX}|summary|result=applied|moved=31|added=2|invoice_note={invoice.note_id}|invoice_number={invoice.invoice_number}|amount=46.80|email_sent=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
