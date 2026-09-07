from __future__ import annotations

import argparse, os, sys
from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from sqlalchemy import func, select
from app.api.routes.admin import BOOKING_STATUSES_ACTIVE, BOOKING_STATUSES_COUNTED_AS_RESERVED, _move_planning_reorganization_booking_occurrence
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, Location, Professor, SessionStatus
from app.models.client_record import ClientNoteEntry
from app.models.user import User

SCRIPT = "MOVE_VIRGILE_TARDIEU_POMPE_17_TO_SCHEFFER_16_20260907"
STUDENT_ID = UUID("1e14b135-af1f-4116-82bb-f874a94b2052")
SOURCE_FIRST_BOOKING_ID = UUID("b769c7a4-865e-40ab-95c5-90fc7d021efc")
TARGET_FIRST_SESSION_ID = UUID("3bdfd4c8-91c6-45ac-bf1c-b5af6c99dbc9")
TARGET_GROUP_ID = UUID("90a2f267-3b69-5ecc-8448-b732b32b68dd")
START_DATE, EXPECTED_COUNT = date(2026, 9, 9), 32
PARIS = ZoneInfo("Europe/Paris")

def local_parts(row):
    tz = ZoneInfo(row.timezone or "Europe/Paris")
    start, end = row.start_at_utc.astimezone(tz), row.end_at_utc.astimezone(tz)
    return start.date(), start.time().replace(tzinfo=None), end.time().replace(tzinfo=None)

def guard_location(db, row, code, name):
    location = db.get(Location, row.location_id)
    if location is None or str(location.code or "").upper() != code or name not in str(location.name or "").casefold():
        raise SystemExit(f"[{SCRIPT}] location_guard_failed session={row.id}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    start_utc = datetime(2026, 9, 9, tzinfo=PARIS).astimezone(timezone.utc)
    with SessionLocal() as db:
        student = db.scalar(select(User).where(User.id == STUDENT_ID).with_for_update())
        if student is None or student.first_name.strip().casefold() != "virgile" or student.last_name.strip().casefold() != "tardieu":
            raise SystemExit(f"[{SCRIPT}] student_guard_failed")
        first_booking = db.scalar(select(Booking).where(Booking.id == SOURCE_FIRST_BOOKING_ID).with_for_update())
        if first_booking is None or first_booking.user_id != STUDENT_ID:
            raise SystemExit(f"[{SCRIPT}] source_booking_guard_failed")
        first_source = db.get(CourseSession, first_booking.session_id)
        if first_source is None or first_source.recurrence_group_id is None:
            raise SystemExit(f"[{SCRIPT}] source_session_guard_failed")
        source_group_id = first_source.recurrence_group_id
        guard_location(db, first_source, "POMPE", "pompe")
        if local_parts(first_source) != (START_DATE, time(17), time(18)):
            raise SystemExit(f"[{SCRIPT}] source_schedule_guard_failed actual={local_parts(first_source)}")
        target_first = db.scalar(select(CourseSession).where(CourseSession.id == TARGET_FIRST_SESSION_ID).with_for_update())
        if target_first is None or target_first.recurrence_group_id != TARGET_GROUP_ID:
            raise SystemExit(f"[{SCRIPT}] target_session_guard_failed")
        guard_location(db, target_first, "SCHEFFER", "scheffer")
        professor = db.get(Professor, target_first.professor_id) if target_first.professor_id else None
        if professor is None or professor.first_name.strip().casefold() != "stephanie" or "araniyadi" not in professor.last_name.strip().casefold():
            raise SystemExit(f"[{SCRIPT}] target_professor_guard_failed")
        if local_parts(target_first) != (START_DATE, time(16), time(17)):
            raise SystemExit(f"[{SCRIPT}] target_schedule_guard_failed actual={local_parts(target_first)}")
        source_rows = db.execute(select(Booking, CourseSession).join(CourseSession, CourseSession.id == Booking.session_id).where(Booking.user_id == STUDENT_ID, Booking.status.in_(BOOKING_STATUSES_ACTIVE), CourseSession.recurrence_group_id == source_group_id, CourseSession.start_at_utc >= start_utc, CourseSession.status == SessionStatus.SCHEDULED).order_by(CourseSession.start_at_utc).with_for_update()).all()
        targets = db.scalars(select(CourseSession).where(CourseSession.recurrence_group_id == TARGET_GROUP_ID, CourseSession.start_at_utc >= start_utc, CourseSession.status == SessionStatus.SCHEDULED).order_by(CourseSession.start_at_utc).with_for_update()).all()
        if len(source_rows) != EXPECTED_COUNT or len(targets) != EXPECTED_COUNT:
            raise SystemExit(f"[{SCRIPT}] series_count_guard_failed source={len(source_rows)} target={len(targets)}")
        source_by_date = {local_parts(s)[0]: (b, s) for b, s in source_rows}
        target_by_date = {local_parts(s)[0]: s for s in targets}
        if len(source_by_date) != EXPECTED_COUNT or len(target_by_date) != EXPECTED_COUNT or set(source_by_date) != set(target_by_date):
            raise SystemExit(f"[{SCRIPT}] calendar_alignment_guard_failed source_dates={sorted(source_by_date)} target_dates={sorted(target_by_date)}")
        existing = db.scalar(select(func.count()).select_from(Booking).join(CourseSession, CourseSession.id == Booking.session_id).where(Booking.user_id == STUDENT_ID, Booking.status.in_(BOOKING_STATUSES_ACTIVE), CourseSession.recurrence_group_id == TARGET_GROUP_ID))
        if int(existing or 0):
            raise SystemExit(f"[{SCRIPT}] target_already_booked count={existing}")
        for target in targets:
            reserved = db.scalar(select(func.count()).select_from(Booking).where(Booking.session_id == target.id, Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED)))
            if int(reserved or 0) >= int(target.capacity_max):
                raise SystemExit(f"[{SCRIPT}] target_full session={target.id} reserved={reserved}")
        days = sorted(source_by_date)
        print(f"[{SCRIPT}] mode={'apply' if args.apply else 'dry-run'} student=Virgile_Tardieu move=32 source=Wed_17_Pompe target=Wed_16_Scheffer first={days[0]} last={days[-1]} price=keep_source notifications=none")
        if not args.apply:
            db.rollback(); print(f"[{SCRIPT}] committed=false"); return
        for day in days:
            booking, source = source_by_date[day]
            ok, detail = _move_planning_reorganization_booking_occurrence(db, booking=booking, source_session=source, target_session=target_by_date[day], now=now, target_price_snapshot=None, lock_price_snapshot=True)
            if not ok:
                raise SystemExit(f"[{SCRIPT}] move_failed day={day} booking={booking.id} detail={detail}")
        db.add(ClientNoteEntry(user_id=STUDENT_ID, author_user_id=None, entry_type="AUTO", message=f"{SCRIPT} - 32 reservations transferees a compter du 09/09/2026 : mercredi 17h Rue de la Pompe vers mercredi 16h Rue Scheffer (Stephanie Araniyadi). Tarifs et rattachements financiers conserves. Aucune notification envoyee."))
        db.flush()
        source_after = db.scalar(select(func.count()).select_from(Booking).join(CourseSession, CourseSession.id == Booking.session_id).where(Booking.user_id == STUDENT_ID, Booking.status.in_(BOOKING_STATUSES_ACTIVE), CourseSession.recurrence_group_id == source_group_id, CourseSession.start_at_utc >= start_utc))
        target_after = db.scalar(select(func.count()).select_from(Booking).join(CourseSession, CourseSession.id == Booking.session_id).where(Booking.user_id == STUDENT_ID, Booking.status.in_(BOOKING_STATUSES_ACTIVE), CourseSession.recurrence_group_id == TARGET_GROUP_ID, CourseSession.start_at_utc >= start_utc))
        if int(source_after or 0) != 0 or int(target_after or 0) != EXPECTED_COUNT:
            raise SystemExit(f"[{SCRIPT}] postcheck_failed source={source_after} target={target_after}")
        db.commit()
        print(f"[{SCRIPT}] committed=true moved=32 source_after=0 target_after={target_after}")

if __name__ == "__main__":
    main()
