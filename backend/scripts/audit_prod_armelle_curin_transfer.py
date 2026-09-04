from __future__ import annotations

import os
import sys
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import BOOKING_STATUSES_ACTIVE, BOOKING_STATUSES_COUNTED_AS_RESERVED
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, Location, Professor
from app.models.user import User


PARIS = ZoneInfo("Europe/Paris")
START_AT = datetime(2026, 9, 10, tzinfo=PARIS).astimezone(timezone.utc)


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).strip().casefold()


def session_label(session: CourseSession, location: Location, course_type: CourseType, professor: Professor | None) -> str:
    local = session.start_at_utc.astimezone(PARIS)
    professor_name = f"{professor.first_name} {professor.last_name}" if professor else "-"
    return (
        f"session={session.id} group={session.recurrence_group_id} local={local.isoformat()} "
        f"location={location.name} activity={course_type.name} professor={professor_name} "
        f"capacity={session.capacity_max}"
    )


def main() -> None:
    with SessionLocal() as db:
        students = db.scalars(select(User).where(User.role == "client")).all()
        matches = [row for row in students if normalized(row.first_name) == "armelle" and normalized(row.last_name) == "curin"]
        if len(matches) != 1:
            raise SystemExit(f"student_guard_failed matches={[(str(row.id), row.first_name, row.last_name) for row in matches]}")
        student = matches[0]
        print(f"student={student.id} name={student.first_name} {student.last_name}")

        source_rows = db.execute(
            select(Booking, CourseSession, Location, CourseType, Professor)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(Location, Location.id == CourseSession.location_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .outerjoin(Professor, Professor.id == CourseSession.professor_id)
            .where(
                Booking.user_id == student.id,
                Booking.status.in_(BOOKING_STATUSES_ACTIVE),
                Location.city.ilike("Bar-le-Duc"),
            )
            .order_by(CourseSession.start_at_utc)
        ).all()
        print(f"active_source_bookings={len(source_rows)}")
        groups: dict[object, list[tuple[Booking, CourseSession, Location, CourseType, Professor | None]]] = {}
        for row in source_rows:
            groups.setdefault(row[1].recurrence_group_id, []).append(row)
        for group_id, rows in groups.items():
            first = rows[0]
            last = rows[-1]
            print(f"SOURCE count={len(rows)} first={session_label(first[1], first[2], first[3], first[4])}")
            print(f"SOURCE last={last[1].start_at_utc.astimezone(PARIS).isoformat()} group={group_id}")
            print(
                "SOURCE prices="
                + str(sorted({(str(row[0].total_incl_vat_snapshot), row[0].currency_snapshot) for row in rows}))
            )

        target_rows = db.execute(
            select(CourseSession, Location, CourseType, Professor)
            .join(Location, Location.id == CourseSession.location_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .outerjoin(Professor, Professor.id == CourseSession.professor_id)
            .where(
                Location.city.ilike("Bar-le-Duc"),
                CourseSession.start_at_utc >= START_AT,
            )
            .order_by(CourseSession.start_at_utc)
        ).all()
        candidate_groups: dict[object, list[tuple[CourseSession, Location, CourseType, Professor | None]]] = {}
        for row in target_rows:
            local = row[0].start_at_utc.astimezone(PARIS)
            if local.weekday() == 3 and local.hour == 17 and local.minute == 0:
                candidate_groups.setdefault(row[0].recurrence_group_id, []).append(row)
        print(f"target_groups={len(candidate_groups)}")
        for group_id, rows in candidate_groups.items():
            first = rows[0]
            counts = []
            for session, *_ in rows:
                reserved = db.scalar(
                    select(func.count()).select_from(Booking).where(
                        Booking.session_id == session.id,
                        Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED),
                    )
                )
                counts.append(int(reserved or 0))
            print(f"TARGET count={len(rows)} first={session_label(first[0], first[1], first[2], first[3])}")
            print(
                f"TARGET last={rows[-1][0].start_at_utc.astimezone(PARIS).isoformat()} group={group_id} "
                f"reserved_min={min(counts)} reserved_max={max(counts)} free_min={min(row[0].capacity_max - count for row, count in zip(rows, counts, strict=True))}"
            )


if __name__ == "__main__":
    main()
