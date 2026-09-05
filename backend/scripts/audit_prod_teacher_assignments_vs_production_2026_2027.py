from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.planning_simulation import PlanningSimulationTeacherAssignment


SCHOOL_YEAR = "2026-2027"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)
END = datetime(2027, 7, 1, tzinfo=timezone.utc)


def professor_name(professor: Professor | None, fallback: str = "Non affecté") -> str:
    if professor is None:
        return fallback
    return " ".join(part for part in (professor.first_name, professor.last_name) if part).strip() or fallback


def main() -> None:
    with SessionLocal() as db:
        assignments = list(
            db.scalars(
                select(PlanningSimulationTeacherAssignment)
                .where(PlanningSimulationTeacherAssignment.school_year_label == SCHOOL_YEAR)
                .order_by(
                    PlanningSimulationTeacherAssignment.slot_key,
                    PlanningSimulationTeacherAssignment.position,
                )
            ).all()
        )
        planned_by_slot: dict[str, list[PlanningSimulationTeacherAssignment]] = defaultdict(list)
        for assignment in assignments:
            planned_by_slot[assignment.slot_key].append(assignment)

        sessions = list(
            db.scalars(
                select(CourseSession).where(
                    CourseSession.start_at_utc >= START,
                    CourseSession.start_at_utc < END,
                    CourseSession.status != SessionStatus.CANCELLED,
                    CourseSession.recurrence_group_id.is_not(None),
                )
            ).all()
        )
        sessions_by_slot: dict[str, list[CourseSession]] = defaultdict(list)
        for session in sessions:
            sessions_by_slot[f"series::{session.recurrence_group_id}"].append(session)

        professor_ids = {
            professor_id
            for assignment in assignments
            if (professor_id := assignment.professor_id) is not None
        } | {session.professor_id for session in sessions if session.professor_id is not None}
        professors = {
            professor.id: professor
            for professor in db.scalars(select(Professor).where(Professor.id.in_(professor_ids))).all()
        }
        location_ids = {session.location_id for session in sessions}
        locations = {
            location.id: location
            for location in db.scalars(select(Location).where(Location.id.in_(location_ids))).all()
        }
        course_type_ids = {session.course_type_id for session in sessions}
        course_types = {
            course_type.id: course_type
            for course_type in db.scalars(select(CourseType).where(CourseType.id.in_(course_type_ids))).all()
        }

        changes: list[dict[str, object]] = []
        deltas_minutes: dict[str, int] = defaultdict(int)
        missing_series: list[dict[str, object]] = []
        matched_series = 0
        for slot_key, planned in planned_by_slot.items():
            slot_sessions = sessions_by_slot.get(slot_key, [])
            if not slot_sessions:
                if slot_key.startswith("series::"):
                    missing_series.append(
                        {
                            "slot_key": slot_key,
                            "planned": [
                                professor_name(professors.get(item.professor_id), item.teacher_label)
                                for item in planned
                            ],
                        }
                    )
                continue
            matched_series += 1
            planned_ids = tuple(item.professor_id for item in planned if item.professor_id is not None)
            actual_groups: dict[UUID | None, list[CourseSession]] = defaultdict(list)
            for session in slot_sessions:
                actual_groups[session.professor_id].append(session)
            if set(actual_groups) == set(planned_ids):
                continue

            sample = min(slot_sessions, key=lambda item: item.start_at_utc)
            location = locations.get(sample.location_id)
            course_type = course_types.get(sample.course_type_id)
            zone = ZoneInfo(session.timezone if (session := sample).timezone else (location.timezone if location else "Europe/Paris"))
            local_sample = sample.start_at_utc.astimezone(zone)
            planned_names = [professor_name(professors.get(item.professor_id), item.teacher_label) for item in planned]
            actual_breakdown = []
            for actual_id, group in sorted(actual_groups.items(), key=lambda item: min(s.start_at_utc for s in item[1])):
                first = min(group, key=lambda item: item.start_at_utc)
                last = max(group, key=lambda item: item.start_at_utc)
                duration_minutes = sum(int((item.end_at_utc - item.start_at_utc).total_seconds() // 60) for item in group)
                actual_name = professor_name(professors.get(actual_id))
                actual_breakdown.append(
                    {
                        "professor": actual_name,
                        "occurrences": len(group),
                        "first_date": first.start_at_utc.astimezone(zone).date().isoformat(),
                        "last_date": last.start_at_utc.astimezone(zone).date().isoformat(),
                        "hours": round(duration_minutes / 60, 2),
                    }
                )
                deltas_minutes[actual_name] += duration_minutes
            total_minutes = sum(
                int((item.end_at_utc - item.start_at_utc).total_seconds() // 60) for item in slot_sessions
            )
            for planned_name in planned_names:
                deltas_minutes[planned_name] -= total_minutes
            changes.append(
                {
                    "slot_key": slot_key,
                    "location": location.name if location else str(sample.location_id),
                    "activity": course_type.name if course_type else sample.title,
                    "weekday": local_sample.strftime("%A"),
                    "time": f"{local_sample:%H:%M}-{sample.end_at_utc.astimezone(zone):%H:%M}",
                    "planned": planned_names,
                    "actual": actual_breakdown,
                    "latest_session_update": max(item.updated_at for item in slot_sessions).isoformat(),
                }
            )

        print(
            "TEACHER_ASSIGNMENT_AUDIT|summary|"
            f"planned_assignments={len(assignments)}|matched_series={matched_series}|"
            f"changed_series={len(changes)}|missing_series={len(missing_series)}"
        )
        print("TEACHER_ASSIGNMENT_AUDIT|changes|" + json.dumps(changes, ensure_ascii=False, default=str))
        print(
            "TEACHER_ASSIGNMENT_AUDIT|workload_delta_hours|"
            + json.dumps(
                {name: round(minutes / 60, 2) for name, minutes in sorted(deltas_minutes.items()) if minutes},
                ensure_ascii=False,
            )
        )
        print("TEACHER_ASSIGNMENT_AUDIT|missing_series|" + json.dumps(missing_series, ensure_ascii=False))


if __name__ == "__main__":
    main()
