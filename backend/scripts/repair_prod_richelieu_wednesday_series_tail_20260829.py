from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, SessionStatus
from app.models.quote import Quote
from app.services.session_teachers import assigned_professor_ids_for_session, replace_session_professors


SCRIPT = "PROD_RICHELIEU_WEDNESDAY_SERIES_TAIL_REPAIR_20260829"
QUOTE_NUMBER = "DV-20260829162719-AD9B"
ACTIVITY_ID = UUID("43c77f63-0ac4-40ca-8e49-fafa4fba3c6e")
LOCATION_ID = UUID("b66fe0d7-2990-4a58-b2f0-360911c611ee")
CURRENT_SERIES_ID = UUID("6db69545-1a1d-4e01-acf9-c25ebcffa54c")
EXPECTED_CURRENT_COUNT = 34
EXPECTED_CURRENT_LAST_DATE = "2027-04-21"
EXPECTED_MISSING_DATES = [
    "2027-04-28",
    "2027-05-05",
    "2027-05-12",
    "2027-05-19",
    "2027-05-26",
    "2027-06-02",
    "2027-06-09",
    "2027-06-16",
]


def _quote_activity_dates(quote: Quote) -> list[str]:
    snapshot = quote.calendar_snapshot if isinstance(quote.calendar_snapshot, dict) else {}
    dates = {
        str(row.get("date") or "").strip()
        for row in snapshot.get("sessions") or []
        if isinstance(row, dict) and str(row.get("activity_id") or "") == str(ACTIVITY_ID)
    }
    return sorted(value for value in dates if value)


def _local_date(session_obj: CourseSession) -> str:
    return session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone)).date().isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore the missing tail of the Richelieu Wednesday series.")
    parser.add_argument("--apply", action="store_true", help="Commit the repair. Default is dry-run.")
    args = parser.parse_args()

    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER))
        if quote is None:
            raise SystemExit(f"[{SCRIPT}] quote_missing")
        quote_dates = _quote_activity_dates(quote)
        if len(quote_dates) != 32 or quote_dates[-8:] != EXPECTED_MISSING_DATES:
            raise SystemExit(f"[{SCRIPT}] quote_snapshot_guard_failed:{quote_dates}")

        series = list(
            db.scalars(
                select(CourseSession)
                .where(CourseSession.recurrence_group_id == CURRENT_SERIES_ID)
                .order_by(CourseSession.start_at_utc.asc())
                .with_for_update()
            ).all()
        )
        existing_dates = [_local_date(row) for row in series]
        already_repaired = all(value in existing_dates for value in EXPECTED_MISSING_DATES)
        if already_repaired:
            print(json.dumps({"script": SCRIPT, "mode": "already-repaired", "series_count": len(series)}))
            db.rollback()
            return
        if len(series) != EXPECTED_CURRENT_COUNT or existing_dates[-1] != EXPECTED_CURRENT_LAST_DATE:
            raise SystemExit(
                f"[{SCRIPT}] current_series_guard_failed:count={len(series)}:last={existing_dates[-1] if existing_dates else None}"
            )

        template = series[-1]
        if (
            template.course_type_id != ACTIVITY_ID
            or template.location_id != LOCATION_ID
            or template.status != SessionStatus.SCHEDULED
            or template.recurrence_until_date is None
            or template.recurrence_until_date.isoformat() != "2027-06-30"
        ):
            raise SystemExit(f"[{SCRIPT}] template_guard_failed")
        course_type = db.get(CourseType, ACTIVITY_ID)
        location = db.get(Location, LOCATION_ID)
        if course_type is None or location is None:
            raise SystemExit(f"[{SCRIPT}] catalog_guard_failed")

        local_zone = ZoneInfo(template.timezone)
        template_local = template.start_at_utc.astimezone(local_zone)
        duration = template.end_at_utc - template.start_at_utc
        deadline_delta = template.start_at_utc - template.auto_cancel_deadline_utc
        professor_ids = assigned_professor_ids_for_session(db, session_obj=template)
        created: list[CourseSession] = []

        for date_value in EXPECTED_MISSING_DATES:
            local_day = datetime.fromisoformat(date_value)
            starts_at = local_day.replace(
                hour=template_local.hour,
                minute=template_local.minute,
                second=template_local.second,
                microsecond=template_local.microsecond,
                tzinfo=local_zone,
            ).astimezone(timezone.utc)
            ends_at = starts_at + duration
            duplicate_count = db.scalar(
                select(func.count(CourseSession.id)).where(
                    CourseSession.course_type_id == ACTIVITY_ID,
                    CourseSession.location_id == LOCATION_ID,
                    CourseSession.start_at_utc == starts_at,
                    CourseSession.status != SessionStatus.CANCELLED,
                )
            )
            if int(duplicate_count or 0) != 0:
                raise SystemExit(f"[{SCRIPT}] duplicate_guard_failed:{date_value}:{duplicate_count}")

            row = CourseSession(
                course_type_id=template.course_type_id,
                billing_entity_snapshot=template.billing_entity_snapshot,
                snapshot_seller_legal_entity_id=template.snapshot_seller_legal_entity_id,
                snapshot_payor_legal_entity_id=template.snapshot_payor_legal_entity_id,
                location_id=template.location_id,
                professor_id=template.professor_id,
                title=template.title,
                description=template.description,
                private_description=template.private_description,
                professor_reminder_note=template.professor_reminder_note,
                group_note=template.group_note,
                internal_note=template.internal_note,
                start_at_utc=starts_at,
                end_at_utc=ends_at,
                is_all_day=template.is_all_day,
                capacity_max=template.capacity_max,
                child_bookings_enabled=template.child_bookings_enabled,
                adult_bookings_enabled=template.adult_bookings_enabled,
                adult_capacity_max=template.adult_capacity_max,
                child_trial_bookings_enabled=template.child_trial_bookings_enabled,
                adult_trial_bookings_enabled=template.adult_trial_bookings_enabled,
                status=SessionStatus.SCHEDULED,
                auto_cancel_deadline_utc=starts_at - deadline_delta,
                auto_cancel_rule_enabled_override=template.auto_cancel_rule_enabled_override,
                auto_cancel_if_booked_less_than_override=template.auto_cancel_if_booked_less_than_override,
                auto_cancel_hours_before_start_override=template.auto_cancel_hours_before_start_override,
                auto_cancel_checked_at=None,
                cancel_reason=None,
                zoom_link=template.zoom_link,
                is_private=template.is_private,
                allow_online_booking=template.allow_online_booking,
                visibility_scope=template.visibility_scope,
                booking_scope=template.booking_scope,
                external_booking_price_ttc=template.external_booking_price_ttc,
                show_external_remaining_seats=template.show_external_remaining_seats,
                timezone=template.timezone,
                recurrence_group_id=CURRENT_SERIES_ID,
                recurrence_rule=template.recurrence_rule,
                recurrence_until_date=template.recurrence_until_date,
                updated_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.flush()
            replace_session_professors(db, session_obj=row, professor_ids=professor_ids)
            created.append(row)

        result = {
            "script": SCRIPT,
            "mode": "apply" if args.apply else "dry-run",
            "series_before": len(series),
            "created": [_local_date(row) for row in created],
            "series_after": len(series) + len(created),
            "quote_sessions": len(quote_dates),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.apply:
            db.commit()
        else:
            db.rollback()


if __name__ == "__main__":
    main()
