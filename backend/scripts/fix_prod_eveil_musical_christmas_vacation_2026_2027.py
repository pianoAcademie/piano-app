from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, SessionStatus
from app.models.quote import Quote, QuoteLine

SCRIPT_PREFIX = "PROD_REPAIR_ASSAS_ADULT_COLLECTIVE_MISSING_SESSIONS"
QUOTE_NUMBER = "DV-20260528100238-F277"
LINE_TITLE = "Cours collectifs ado/adultes"
COURSE_ID = "43c77f63-0ac4-40ca-8e49-fafa4fba3c6e"
LOCATION_ID = "1be3c4dc-2f55-4712-bcf9-32a4624ff1ad"
SERIES_KEY = "071696b4-b6db-45eb-ab91-5803b367c707"
TARGET_DATES = (date(2027, 3, 31), date(2027, 5, 19))
START_TIME = time(19, 0)
END_TIME = time(20, 0)
TARGET_QUANTITY = Decimal("32.00")


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _q2(value: Decimal) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _local_parts(session_obj: CourseSession) -> tuple[date, time, time]:
    tz = ZoneInfo(session_obj.timezone or "Europe/Paris")
    start = session_obj.start_at_utc.astimezone(tz)
    end = session_obj.end_at_utc.astimezone(tz)
    return start.date(), start.time().replace(tzinfo=None), end.time().replace(tzinfo=None)


def _nearest_template(sessions: list[CourseSession], target_date: date) -> CourseSession:
    candidates = [
        session_obj
        for session_obj in sessions
        if _local_parts(session_obj)[1:] == (START_TIME, END_TIME)
    ]
    if not candidates:
        raise RuntimeError("No template session found")
    return min(candidates, key=lambda session_obj: abs((_local_parts(session_obj)[0] - target_date).days))


def _copy_session(template: CourseSession, *, target_date: date) -> CourseSession:
    tz = ZoneInfo(template.timezone or "Europe/Paris")
    start_utc = datetime.combine(target_date, START_TIME, tzinfo=tz).astimezone(timezone.utc)
    end_utc = datetime.combine(target_date, END_TIME, tzinfo=tz).astimezone(timezone.utc)
    deadline_delta = template.start_at_utc - template.auto_cancel_deadline_utc
    if deadline_delta.total_seconds() <= 0:
        deadline_delta = template.end_at_utc - template.start_at_utc
    return CourseSession(
        course_type_id=template.course_type_id,
        billing_entity_snapshot=template.billing_entity_snapshot,
        snapshot_seller_legal_entity_id=template.snapshot_seller_legal_entity_id,
        snapshot_payor_legal_entity_id=template.snapshot_payor_legal_entity_id,
        location_id=template.location_id,
        professor_id=template.professor_id,
        substitute_teacher_id=template.substitute_teacher_id,
        substitute_set_at=template.substitute_set_at,
        substitute_set_by=template.substitute_set_by,
        substitute_note=template.substitute_note,
        title=template.title,
        description=template.description,
        private_description=template.private_description,
        group_note=template.group_note,
        professor_reminder_note=template.professor_reminder_note,
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        is_all_day=template.is_all_day,
        capacity_max=template.capacity_max,
        status=SessionStatus.SCHEDULED,
        auto_cancel_deadline_utc=start_utc - deadline_delta,
        cancel_reason=None,
        zoom_link=template.zoom_link,
        is_private=template.is_private,
        allow_online_booking=template.allow_online_booking,
        visibility_scope=template.visibility_scope,
        booking_scope=template.booking_scope,
        external_booking_price_ttc=template.external_booking_price_ttc,
        show_external_remaining_seats=template.show_external_remaining_seats,
        timezone=template.timezone,
        recurrence_group_id=template.recurrence_group_id,
        recurrence_rule=template.recurrence_rule,
        recurrence_until_date=template.recurrence_until_date,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the Assas quote and planning repair.")
    args = parser.parse_args()

    with SessionLocal() as db:
        sessions = db.scalars(
            select(CourseSession)
            .where(
                CourseSession.course_type_id == COURSE_ID,
                CourseSession.location_id == LOCATION_ID,
                CourseSession.recurrence_group_id == SERIES_KEY,
                CourseSession.status == SessionStatus.SCHEDULED,
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()

        created_dates: list[str] = []
        already_present = 0
        would_create = 0
        for target_date in TARGET_DATES:
            template = _nearest_template(sessions, target_date)
            tz = ZoneInfo(template.timezone or "Europe/Paris")
            start_utc = datetime.combine(target_date, START_TIME, tzinfo=tz).astimezone(timezone.utc)
            end_utc = datetime.combine(target_date, END_TIME, tzinfo=tz).astimezone(timezone.utc)
            existing = db.scalar(
                select(CourseSession.id)
                .where(
                    CourseSession.course_type_id == COURSE_ID,
                    CourseSession.location_id == LOCATION_ID,
                    CourseSession.status == SessionStatus.SCHEDULED,
                    CourseSession.start_at_utc == start_utc,
                    CourseSession.end_at_utc == end_utc,
                )
                .limit(1)
            )
            if existing is not None:
                already_present += 1
                _print(f"already_present date={target_date.isoformat()}|session={existing}")
                continue
            would_create += 1
            _print(f"create_session date={target_date.isoformat()}|template={template.id}|apply={args.apply}")
            if args.apply:
                session_obj = _copy_session(template, target_date=target_date)
                db.add(session_obj)
                db.flush()
                sessions.append(session_obj)
                created_dates.append(target_date.isoformat())

        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).with_for_update().limit(1))
        if quote is None:
            raise RuntimeError(f"Quote not found: {QUOTE_NUMBER}")
        line = db.scalar(
            select(QuoteLine)
            .where(QuoteLine.quote_id == quote.id, QuoteLine.title == LINE_TITLE)
            .with_for_update()
            .limit(1)
        )
        if line is None:
            raise RuntimeError(f"Quote line not found: {QUOTE_NUMBER} / {LINE_TITLE}")

        old_quantity = Decimal(line.quantity or 0)
        old_amount_ttc = Decimal(line.amount_ttc or 0)
        new_amount_ttc = _q2(Decimal(line.unit_price_ttc or 0) * TARGET_QUANTITY)
        _print(
            f"line_update line={line.id}|old_quantity={old_quantity}|new_quantity={TARGET_QUANTITY}|"
            f"old_amount_ttc={old_amount_ttc}|new_amount_ttc={new_amount_ttc}|apply={args.apply}"
        )

        quote_total_ttc = Decimal(quote.total_ttc or 0)
        if args.apply:
            line.quantity = TARGET_QUANTITY
            line.amount_ht = _q2(Decimal(line.unit_price_ht or 0) * TARGET_QUANTITY)
            line.amount_vat = _q2(Decimal(line.unit_vat_amount or 0) * TARGET_QUANTITY)
            line.amount_ttc = new_amount_ttc
            meta = dict(line.meta or {})
            meta["typeform_planned_quantity"] = str(TARGET_QUANTITY)
            meta["planning_session_limit"] = int(TARGET_QUANTITY)
            line.meta = meta
            line.updated_at = _utcnow()
            db.add(line)
            db.flush()

            lines_total = db.scalar(
                select(func.coalesce(func.sum(QuoteLine.amount_ttc), Decimal("0"))).where(QuoteLine.quote_id == quote.id)
            )
            quote_total_ttc = _q2(Decimal(lines_total or 0))
            quote.total_ttc = quote_total_ttc
            quote.price_snapshot = {
                "catalog_id": str(quote.pricing_catalog_id) if quote.pricing_catalog_id else None,
                "currency": quote.currency,
                "lines_total_ttc": str(quote_total_ttc),
                "total_ttc": str(quote_total_ttc),
            }
            quote.document_status = "stale"
            quote.document_hash = None
            quote.document_generated_at = None
            quote.document_snapshot_id = None
            quote.updated_at = _utcnow()
            db.add(quote)
            db.commit()
        else:
            db.rollback()

        summary = (
            f"apply={args.apply}|created={len(created_dates)}|would_create={would_create}|"
            f"already_present={already_present}|created_dates={','.join(created_dates) or '-'}|"
            f"old_quantity={old_quantity}|target_quantity={TARGET_QUANTITY}|"
            f"old_amount_ttc={old_amount_ttc}|target_amount_ttc={new_amount_ttc}|quote_total_ttc={quote_total_ttc}"
        )
        _print(f"summary {summary}")
        print(f"::notice title=Assas adult collective missing sessions repair::{summary}")


if __name__ == "__main__":
    main()
