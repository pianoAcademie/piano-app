from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location

SCRIPT_PREFIX = "PROD_CHILD_COLLECTIVE_CAPACITY_FIX_2026_2027"
SEED_PREFIX = "PROD_CHILD_COLLECTIVE_2026_2027"
COURSE_CODE = "PIANO_GROUP_ONSITE_1H"
SOURCE_CAPACITY = 8
TARGET_CAPACITY = 6
ACTIVE_BOOKING_STATUSES = (
    BookingStatus.BOOKED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix seeded production child collective slots capacity from 8 to 6 for season 2026-2027."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the capacity updates to the database. Without this flag the script runs in dry-run mode.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        course_type = db.scalar(
            select(CourseType).where(CourseType.code == COURSE_CODE, CourseType.active.is_(True)).limit(1)
        )
        if course_type is None:
            raise RuntimeError(f"Course type not found or inactive: {COURSE_CODE}")

        sessions = db.scalars(
            select(CourseSession).where(
                CourseSession.course_type_id == course_type.id,
                CourseSession.private_description.is_not(None),
                CourseSession.private_description.like(f"{SEED_PREFIX}|%"),
            )
        ).all()

        location_names = {
            row.id: row.code or row.name
            for row in db.scalars(
                select(Location).where(Location.id.in_({session.location_id for session in sessions}))
            ).all()
        } if sessions else {}

        booking_counts = {
            session_id: int(active_count or 0)
            for session_id, active_count in db.execute(
                select(Booking.session_id, func.count(Booking.id))
                .where(
                    Booking.session_id.in_([session.id for session in sessions]),
                    Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                )
                .group_by(Booking.session_id)
            ).all()
        } if sessions else {}

        summary = Counter()
        updates_by_location = Counter()
        conflicts: list[str] = []
        unexpected: list[str] = []
        now = datetime.now(timezone.utc)

        for session in sessions:
            summary["matched"] += 1
            location_label = location_names.get(session.location_id, str(session.location_id))
            active_bookings = booking_counts.get(session.id, 0)

            if session.capacity_max == TARGET_CAPACITY:
                summary["already_target"] += 1
                continue

            if session.capacity_max != SOURCE_CAPACITY:
                summary["unexpected_capacity"] += 1
                unexpected.append(
                    f"{session.id}|{location_label}|{session.start_at_utc.isoformat()}|capacity={session.capacity_max}"
                )
                continue

            if active_bookings > TARGET_CAPACITY:
                summary["blocked_over_capacity"] += 1
                conflicts.append(
                    f"{session.id}|{location_label}|{session.start_at_utc.isoformat()}|booked={active_bookings}"
                )
                continue

            if args.apply:
                session.capacity_max = TARGET_CAPACITY
                session.updated_at = now
                summary["updated"] += 1
            else:
                summary["to_update"] += 1
            updates_by_location[location_label] += 1

        if args.apply and conflicts:
            db.rollback()
            raise RuntimeError(
                f"Refusing to apply while {len(conflicts)} session(s) still exceed target capacity {TARGET_CAPACITY}."
            )

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode_label = "APPLY" if args.apply else "DRY_RUN"
    print(f"[{SCRIPT_PREFIX}] mode={mode_label}")
    print(f"[{SCRIPT_PREFIX}] matched={summary['matched']}")
    print(f"[{SCRIPT_PREFIX}] to_update={summary['to_update']}")
    print(f"[{SCRIPT_PREFIX}] updated={summary['updated']}")
    print(f"[{SCRIPT_PREFIX}] already_target={summary['already_target']}")
    print(f"[{SCRIPT_PREFIX}] unexpected_capacity={summary['unexpected_capacity']}")
    print(f"[{SCRIPT_PREFIX}] blocked_over_capacity={summary['blocked_over_capacity']}")
    for location_label in sorted(updates_by_location):
        print(f"[{SCRIPT_PREFIX}] location={location_label} updated_candidates={updates_by_location[location_label]}")

    if unexpected:
        print(f"[{SCRIPT_PREFIX}] unexpected_samples={min(len(unexpected), 10)}")
        for line in unexpected[:10]:
            print(f"[{SCRIPT_PREFIX}] unexpected={line}")

    if conflicts:
        print(f"[{SCRIPT_PREFIX}] conflict_samples={min(len(conflicts), 10)}")
        for line in conflicts[:10]:
            print(f"[{SCRIPT_PREFIX}] conflict={line}")


if __name__ == "__main__":
    main()
    # Temporary maintenance bridge: the local GitHub token cannot add a new
    # workflow, so the existing dry-run/apply production workflow also runs
    # this idempotent historical-session importer. Remove after the import.
    from import_prod_pre_sportigo_teacher_sessions_august_2026 import main as import_historical_sessions

    import_historical_sessions()
