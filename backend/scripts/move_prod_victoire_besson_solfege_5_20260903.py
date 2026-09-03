"""Move Victoire Besson from Thursday solfege 4 to Monday solfege 5.

Dry-run by default. Moves the 26 future bookings one-to-one by ISO week,
preserves their subscription and price snapshots, records an internal change,
and sends no notification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, SessionStatus
from app.models.client_record import StudentQuoteChange
from app.models.user import User

STUDENT_ID = UUID("c8e1cdb4-2fe5-4368-97c4-331135311ac1")
SOURCE_SERIES_ID = UUID("8f3a9457-07b2-4d50-b28b-702fbe175630")
TARGET_SERIES_ID = UUID("126c2e9e-8e44-4932-a0da-0b942f073915")
SOURCE_LEVEL = "Solfège niveau 4"
TARGET_LEVEL = "Solfège niveau 5"
TARGET_START = "19:35"
TARGET_END = "20:05"
EXPECTED_COUNT = 26


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def local_parts(session: CourseSession) -> tuple[str, str, str, tuple[int, int]]:
    zone = ZoneInfo(session.timezone or "Europe/Paris")
    start = session.start_at_utc.astimezone(zone)
    end = session.end_at_utc.astimezone(zone)
    iso = start.isocalendar()
    return start.date().isoformat(), start.strftime("%H:%M"), end.strftime("%H:%M"), (iso.year, iso.week)


def run(*, apply: bool) -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        if not apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        student_stmt = select(User).where(User.id == STUDENT_ID)
        student = db.scalar(student_stmt.with_for_update() if apply else student_stmt)
        require(student is not None, "Student not found")
        require((student.first_name or "").casefold() == "victoire" and (student.last_name or "").casefold() == "besson", "Student identity changed")

        source_stmt = (
            select(Booking, CourseSession, CourseType)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .where(
                Booking.user_id == STUDENT_ID,
                Booking.status == BookingStatus.BOOKED,
                CourseSession.recurrence_group_id == SOURCE_SERIES_ID,
                CourseSession.start_at_utc > now,
            )
            .order_by(CourseSession.start_at_utc)
        )
        source_rows = list(db.execute(source_stmt).all())
        if not source_rows:
            target_count = db.scalar(
                select(func.count(Booking.id))
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .where(
                    Booking.user_id == STUDENT_ID,
                    Booking.status == BookingStatus.BOOKED,
                    CourseSession.recurrence_group_id == TARGET_SERIES_ID,
                    CourseSession.start_at_utc > now,
                    CourseSession.start_at_utc.in_(
                        select(CourseSession.start_at_utc).where(CourseSession.recurrence_group_id == TARGET_SERIES_ID)
                    ),
                )
            ) or 0
            require(target_count == EXPECTED_COUNT, "Neither the expected source nor a complete target assignment was found")
            return {"mode": "already_moved", "student": "Victoire Besson", "bookings": target_count}

        require(len(source_rows) == EXPECTED_COUNT, f"Expected {EXPECTED_COUNT} source bookings, found {len(source_rows)}")
        require(all(course.name == SOURCE_LEVEL for _, _, course in source_rows), "Source activity is not exclusively solfege level 4")
        require(all(session.status == SessionStatus.SCHEDULED for _, session, _ in source_rows), "A source lesson is no longer scheduled")
        require(all(session.start_at_utc > now for _, session, _ in source_rows), "A past lesson would be changed")
        subscription_ids = {booking.client_plan_subscription_id for booking, _, _ in source_rows}
        require(len(subscription_ids) == 1 and None not in subscription_ids, "Source bookings are not attached to one subscription")
        require(all(Decimal(booking.total_incl_vat_snapshot) == Decimal("0.00") for booking, _, _ in source_rows), "Unexpected financial amount on solfege")

        target_stmt = (
            select(CourseSession, CourseType)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .where(
                CourseSession.recurrence_group_id == TARGET_SERIES_ID,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc > now,
            )
            .order_by(CourseSession.start_at_utc)
        )
        target_rows = []
        for session, course in db.execute(target_stmt).all():
            _, start_time, end_time, _ = local_parts(session)
            if course.name == TARGET_LEVEL and start_time == TARGET_START and end_time == TARGET_END:
                target_rows.append((session, course))
        require(len(target_rows) == EXPECTED_COUNT, f"Expected {EXPECTED_COUNT} target lessons, found {len(target_rows)}")
        target_by_week = {local_parts(session)[3]: session for session, _ in target_rows}
        require(len(target_by_week) == EXPECTED_COUNT, "Target series contains duplicate ISO weeks")

        pairs = []
        for booking, source, _ in source_rows:
            source_date, source_start, source_end, week = local_parts(source)
            require(source_start == "19:00" and source_end == "19:45", f"Unexpected source time on {source_date}")
            target = target_by_week.get(week)
            require(target is not None, f"No target lesson in ISO week {week}")
            target_date, _, _, _ = local_parts(target)
            require((datetime.fromisoformat(source_date).date() - datetime.fromisoformat(target_date).date()).days == 3, f"Source/target week mismatch for {source_date}")
            require(source.location_id == target.location_id, "Online location changed")
            active_count = db.scalar(
                select(func.count(Booking.id)).where(
                    Booking.session_id == target.id,
                    Booking.status.in_([BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW]),
                )
            ) or 0
            require(active_count < target.capacity_max, f"Target lesson is full on {target_date}")
            conflict = db.scalar(
                select(Booking.id).where(
                    Booking.user_id == STUDENT_ID,
                    Booking.session_id == target.id,
                    Booking.status.in_([BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW]),
                ).limit(1)
            )
            require(conflict is None, f"Student is already booked on target {target_date}")
            pairs.append((booking, source, target))

        result = {
            "mode": "apply" if apply else "dry_run",
            "student": "Victoire Besson",
            "from": "Solfège niveau 4 — jeudi 19:00-19:45",
            "to": "Solfège niveau 5 — lundi 19:35-20:05",
            "bookings": len(pairs),
            "first_target_date": local_parts(pairs[0][2])[0],
            "last_target_date": local_parts(pairs[-1][2])[0],
            "financial_impact_ttc": "0.00",
            "notifications_sent": 0,
        }
        if apply:
            before = []
            after = []
            for booking, source, target in pairs:
                before.append({"booking_id": str(booking.id), "session_id": str(source.id), "local_date": local_parts(source)[0]})
                booking.session_id = target.id
                booking.internal_note = "Changement demandé : passage du solfège niveau 4 du jeudi au niveau 5 du lundi. Tarif conservé, sans notification."
                after.append({"booking_id": str(booking.id), "session_id": str(target.id), "local_date": local_parts(target)[0]})
                db.add(booking)
            change = StudentQuoteChange(
                user_id=STUDENT_ID,
                student_user_id=STUDENT_ID,
                change_type="ACTIVITY_AND_SLOT_CHANGE",
                status="VALIDATED",
                requested_by="Administration — demande utilisateur du 03/09/2026",
                effective_date=datetime.fromisoformat(result["first_target_date"]).date(),
                title="Victoire Besson — passage du solfège niveau 4 au niveau 5",
                description="Déplacement de 26 réservations futures du jeudi 19h au lundi 19h35, sans notification.",
                before_snapshot={"series_id": str(SOURCE_SERIES_ID), "activity": SOURCE_LEVEL, "sessions": before},
                after_snapshot={"series_id": str(TARGET_SERIES_ID), "activity": TARGET_LEVEL, "sessions": after},
                financial_impact_ttc=Decimal("0.00"),
                currency="EUR",
                billing_action="NONE",
                internal_note="Contrat et snapshots tarifaires conservés. Aucune notification envoyée.",
            )
            db.add(change)
            db.flush()
            result["change_id"] = str(change.id)
            db.commit()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    print(json.dumps(run(apply=parser.parse_args().apply), indent=2, ensure_ascii=False))
