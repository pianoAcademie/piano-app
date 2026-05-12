from __future__ import annotations

from collections import defaultdict
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, SessionStatus


def _local_zone(name: str | None) -> ZoneInfo:
    return ZoneInfo(name or "Europe/Paris")


def main() -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(CourseSession, CourseType.name, Location.name)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                CourseSession.recurrence_group_id.is_not(None),
                CourseSession.recurrence_rule == "WEEKLY@UTC",
                CourseSession.status == SessionStatus.SCHEDULED,
            )
            .order_by(CourseSession.recurrence_group_id.asc(), CourseSession.start_at_utc.asc())
        ).all()

        grouped: dict[str, list[CourseSession]] = defaultdict(list)
        labels: dict[str, tuple[str, str]] = {}
        for session_obj, activity_name, location_name in rows:
            group_id = str(session_obj.recurrence_group_id)
            grouped[group_id].append(session_obj)
            labels[group_id] = (activity_name, location_name)

        changed = 0
        for group_id, sessions in grouped.items():
            anchor = sessions[0].start_at_utc.astimezone(_local_zone(sessions[0].timezone))
            anchor_hour = anchor.hour
            anchor_minute = anchor.minute
            anchor_second = anchor.second
            anchor_microsecond = anchor.microsecond

            for session_obj in sessions:
                zone = _local_zone(session_obj.timezone)
                current_local = session_obj.start_at_utc.astimezone(zone)
                target_local = current_local.replace(
                    hour=anchor_hour,
                    minute=anchor_minute,
                    second=anchor_second,
                    microsecond=anchor_microsecond,
                )
                target_start = target_local.astimezone(timezone.utc)
                duration = session_obj.end_at_utc - session_obj.start_at_utc
                deadline_delta = session_obj.start_at_utc - session_obj.auto_cancel_deadline_utc
                if session_obj.start_at_utc.replace(microsecond=0) != target_start.replace(microsecond=0):
                    session_obj.start_at_utc = target_start
                    session_obj.end_at_utc = target_start + duration
                    session_obj.auto_cancel_deadline_utc = target_start - deadline_delta
                    changed += 1
                session_obj.recurrence_rule = "WEEKLY@LOCAL"

        db.commit()

        print(f"converted_groups={len(grouped)} shifted_sessions={changed}")
        for group_id in sorted(grouped, key=lambda value: labels[value]):
            activity_name, location_name = labels[group_id]
            print(f"{group_id} | {activity_name} | {location_name} | sessions={len(grouped[group_id])}")


if __name__ == "__main__":
    main()
