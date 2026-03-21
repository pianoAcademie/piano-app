from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.api.routes.admin import (
    _has_vacation_on_day,
    _is_blocked_by_school_calendar,
    _recurrence_datetimes_until,
    _serialize_recurrence_rule,
    _utc_from_local_wall_clock,
)
from app.db.session import SessionLocal
from app.models.catalog import (
    CourseSession,
    CourseType,
    DeliveryMode,
    Location,
    PlanningCourseType,
    SessionStatus,
)
from app.models.ops import LegalEntity
from app.services.invoice_documents import normalize_billing_entity

SEED_PREFIX = "LOCAL_H1_2026"
DATE_START = date(2026, 1, 1)
DATE_END = date(2026, 6, 30)
LOCAL_PARIS_TZ = "Europe/Paris"
EVEIL_ACTIVITY_CODE = "ACT_EVEIL_MUSICAL_98E099"


@dataclass(frozen=True)
class SeriesDefinition:
    key: str
    course_code: str
    location_code: str
    weekday: int
    hour: int
    minute: int = 0
    interval: int = 1
    start_date: date = DATE_START
    end_date: date = DATE_END
    timezone_name: str | None = None
    duration_minutes: int | None = None
    capacity_max: int | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stable_uuid(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"piano-academie:{SEED_PREFIX}:{name}")


def _first_occurrence_on_or_after(start_date: date, weekday: int) -> date:
    days_ahead = (weekday - start_date.weekday()) % 7
    return start_date + timedelta(days=days_ahead)


def _session_marker(series_key: str, occurrence_day: date, *, hour: int, minute: int) -> str:
    return f"{SEED_PREFIX}|{series_key}|{occurrence_day.isoformat()}|{hour:02d}:{minute:02d}"


def _ensure_eveil_activity(db) -> CourseType:
    activity = db.scalar(select(CourseType).where(CourseType.code == EVEIL_ACTIVITY_CODE).limit(1))
    if activity is not None:
        return activity

    legal_entity = db.scalar(
        select(LegalEntity)
        .where(
            LegalEntity.name == "PIANO ACADEMIE",
            LegalEntity.is_active.is_(True),
        )
        .limit(1)
    )
    if legal_entity is None:
        raise RuntimeError("Legal entity 'PIANO ACADEMIE' introuvable en base locale")

    activity = CourseType(
        code=EVEIL_ACTIVITY_CODE,
        name="Eveil musical",
        description="Activite locale H1 2026 pour tests planning/intake/devis.",
        service_code="EVEIL_MUSICAL",
        billing_entity_code=normalize_billing_entity("PIANO_ACADEMIE"),
        seller_legal_entity_id=legal_entity.id,
        payor_legal_entity_id=legal_entity.id,
        credit_type_id=None,
        duration_minutes=60,
        color_hex="#E6A85F",
        mode=DeliveryMode.ONSITE,
        requires_professor=True,
        allows_student_bookings=True,
        default_capacity=6,
        default_hourly_rate=None,
        default_course_rate_ttc=Decimal("22.00"),
        exclude_holidays_in_recurrence=True,
        exclude_school_vacations_in_recurrence=True,
        active=True,
        created_at=_utcnow(),
    )
    db.add(activity)
    db.flush()
    return activity


def _ensure_eveil_activity_flags(activity: CourseType) -> bool:
    changed = False
    if int(activity.duration_minutes or 0) != 60:
        activity.duration_minutes = 60
        changed = True
    if activity.default_course_rate_ttc != Decimal("22.00"):
        activity.default_course_rate_ttc = Decimal("22.00")
        changed = True
    if activity.default_hourly_rate is not None:
        activity.default_hourly_rate = None
        changed = True
    if not bool(activity.exclude_holidays_in_recurrence):
        activity.exclude_holidays_in_recurrence = True
        changed = True
    if not bool(activity.exclude_school_vacations_in_recurrence):
        activity.exclude_school_vacations_in_recurrence = True
        changed = True
    return changed


def _start_of_utc_day(value: datetime) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _ensure_planning_mapping(db, *, location: Location, course_type: CourseType) -> bool:
    existing = db.scalar(
        select(PlanningCourseType)
        .where(
            PlanningCourseType.location_id == location.id,
            PlanningCourseType.course_type_id == course_type.id,
        )
        .limit(1)
    )
    if existing is not None:
        return False

    max_display_order = db.scalar(
        select(func.max(PlanningCourseType.display_order)).where(PlanningCourseType.location_id == location.id)
    )
    db.add(
        PlanningCourseType(
            location_id=location.id,
            course_type_id=course_type.id,
            display_order=int(max_display_order or 0) + 1,
            created_at=_utcnow(),
        )
    )
    return True


def _build_series_definitions() -> list[SeriesDefinition]:
    definitions: list[SeriesDefinition] = []

    # Eveil musical
    definitions.extend(
        [
            SeriesDefinition("eveil-pompe-wed-10", EVEIL_ACTIVITY_CODE, "POMPE", weekday=2, hour=10),
            SeriesDefinition("eveil-pompe-wed-16", EVEIL_ACTIVITY_CODE, "POMPE", weekday=2, hour=16),
            SeriesDefinition("eveil-pompe-sat-10", EVEIL_ACTIVITY_CODE, "POMPE", weekday=5, hour=10),
            SeriesDefinition("eveil-assas-wed-16", EVEIL_ACTIVITY_CODE, "ASSAS", weekday=2, hour=16),
            SeriesDefinition("eveil-assas-sat-10", EVEIL_ACTIVITY_CODE, "ASSAS", weekday=5, hour=10),
            SeriesDefinition("eveil-richelieu-wed-16", EVEIL_ACTIVITY_CODE, "RICHELIEU", weekday=2, hour=16),
            SeriesDefinition("eveil-richelieu-sat-10", EVEIL_ACTIVITY_CODE, "RICHELIEU", weekday=5, hour=10),
        ]
    )

    # Enfants collectif online
    for weekday, weekday_key in enumerate(["mon", "tue", "wed", "thu", "fri"]):
        for hour in (18, 19):
            definitions.append(
                SeriesDefinition(
                    key=f"online-child-{weekday_key}-{hour:02d}",
                    course_code="PIANO_GROUP_ONLINE_1H",
                    location_code="ONLINE",
                    weekday=weekday,
                    hour=hour,
                    timezone_name=LOCAL_PARIS_TZ,
                )
            )

    # Enfants collectif onsite
    onsite_locations = ("SCHEFFER", "POMPE", "RICHELIEU", "ASSAS")
    for location_code in onsite_locations:
        for weekday, weekday_key in ((0, "mon"), (1, "tue"), (3, "thu"), (4, "fri")):
            for hour in (17, 18):
                definitions.append(
                    SeriesDefinition(
                        key=f"onsite-child-{location_code.lower()}-{weekday_key}-{hour:02d}",
                        course_code="PIANO_GROUP_ONSITE_1H",
                        location_code=location_code,
                        weekday=weekday,
                        hour=hour,
                    )
                )
        for hour in (10, 11, 14, 15, 16, 17, 18):
            definitions.append(
                SeriesDefinition(
                    key=f"onsite-child-{location_code.lower()}-wed-{hour:02d}",
                    course_code="PIANO_GROUP_ONSITE_1H",
                    location_code=location_code,
                    weekday=2,
                    hour=hour,
                )
            )

    # MasterClass Concours
    definitions.extend(
        [
            SeriesDefinition(
                key="masterclass-scheffer-sat-09",
                course_code="ACT_MASTERCLASS_D84DC5",
                location_code="SCHEFFER",
                weekday=5,
                hour=9,
                interval=2,
                start_date=date(2026, 1, 10),
                duration_minutes=180,
            ),
            SeriesDefinition(
                key="masterclass-scheffer-sat-1330",
                course_code="ACT_MASTERCLASS_D84DC5",
                location_code="SCHEFFER",
                weekday=5,
                hour=13,
                minute=30,
                interval=2,
                start_date=date(2026, 1, 10),
                duration_minutes=180,
            ),
            SeriesDefinition(
                key="masterclass-richelieu-sat-09",
                course_code="ACT_MASTERCLASS_D84DC5",
                location_code="RICHELIEU",
                weekday=5,
                hour=9,
                interval=2,
                start_date=date(2026, 1, 17),
                duration_minutes=180,
            ),
            SeriesDefinition(
                key="masterclass-richelieu-sat-14",
                course_code="ACT_MASTERCLASS_D84DC5",
                location_code="RICHELIEU",
                weekday=5,
                hour=14,
                interval=2,
                start_date=date(2026, 1, 17),
                duration_minutes=180,
            ),
        ]
    )

    return definitions


def main() -> None:
    created_activity = False
    updated_activity = False
    created_mappings = 0
    created_sessions = 0
    updated_sessions = 0
    unchanged_sessions = 0
    removed_sessions = 0
    definitions = _build_series_definitions()

    with SessionLocal() as db:
        eveil = db.scalar(select(CourseType).where(CourseType.code == EVEIL_ACTIVITY_CODE).limit(1))
        if eveil is None:
            eveil = _ensure_eveil_activity(db)
            created_activity = True
        elif _ensure_eveil_activity_flags(eveil):
            updated_activity = True

        course_types = {
            row.code: row
            for row in db.scalars(
                select(CourseType).where(
                    CourseType.code.in_(
                        [
                            EVEIL_ACTIVITY_CODE,
                            "PIANO_GROUP_ONLINE_1H",
                            "PIANO_GROUP_ONSITE_1H",
                            "ACT_MASTERCLASS_D84DC5",
                        ]
                    )
                )
            ).all()
        }
        missing_codes = {item.course_code for item in definitions} - set(course_types)
        if missing_codes:
            raise RuntimeError(f"Activites introuvables: {', '.join(sorted(missing_codes))}")

        locations = {
            row.code: row
            for row in db.scalars(
                select(Location).where(
                    Location.code.in_(
                        [
                            "ONLINE",
                            "SCHEFFER",
                            "POMPE",
                            "RICHELIEU",
                            "ASSAS",
                        ]
                    )
                )
            ).all()
        }
        missing_locations = {item.location_code for item in definitions} - set(locations)
        if missing_locations:
            raise RuntimeError(f"Lieux introuvables: {', '.join(sorted(missing_locations))}")

        for location_code in ("POMPE", "ASSAS", "RICHELIEU"):
            if _ensure_planning_mapping(db, location=locations[location_code], course_type=course_types[EVEIL_ACTIVITY_CODE]):
                created_mappings += 1
        if _ensure_planning_mapping(db, location=locations["RICHELIEU"], course_type=course_types["ACT_MASTERCLASS_D84DC5"]):
            created_mappings += 1

        series_occurrence_counts: dict[str, int] = {}
        desired_markers: set[str] = set()
        calendar_skip_cache: dict[str, object] = {}

        for definition in definitions:
            course_type = course_types[definition.course_code]
            location = locations[definition.location_code]
            session_timezone = definition.timezone_name or location.timezone
            local_anchor_day = _first_occurrence_on_or_after(definition.start_date, definition.weekday)
            local_anchor = datetime(
                local_anchor_day.year,
                local_anchor_day.month,
                local_anchor_day.day,
                definition.hour,
                definition.minute,
            )
            anchor_start_at_utc = _utc_from_local_wall_clock(local_anchor, timezone_name=session_timezone)
            recurrence_rule = _serialize_recurrence_rule(
                frequency="WEEKLY",
                interval=definition.interval,
                time_basis="LOCAL",
            )
            recurrence_group_id = _stable_uuid(definition.key)
            occurrence_starts = _recurrence_datetimes_until(
                anchor_start_at_utc=anchor_start_at_utc,
                recurrence_frequency="WEEKLY",
                recurrence_interval=definition.interval,
                recurrence_until_date=definition.end_date,
                session_timezone=session_timezone,
                recurrence_time_basis="LOCAL",
                limit=400,
            )
            series_occurrence_counts[definition.key] = len(occurrence_starts)

            duration_minutes = int(definition.duration_minutes or course_type.duration_minutes)
            capacity_max = int(definition.capacity_max or course_type.default_capacity)

            for start_at_utc in occurrence_starts:
                day_start_utc = _start_of_utc_day(start_at_utc)
                if _has_vacation_on_day(db, location_id=location.id, day_start_utc=day_start_utc):
                    continue
                if _is_blocked_by_school_calendar(
                    db,
                    location_id=location.id,
                    location_timezone=location.timezone,
                    starts_at_utc=start_at_utc,
                    include_holidays=bool(course_type.exclude_holidays_in_recurrence),
                    include_school_vacations=bool(course_type.exclude_school_vacations_in_recurrence),
                    cache=calendar_skip_cache,
                ):
                    continue

                # Keep the marker keyed on the local calendar day in the session timezone.
                local_day = start_at_utc.astimezone(ZoneInfo(session_timezone)).date()
                marker = _session_marker(definition.key, local_day, hour=definition.hour, minute=definition.minute)
                desired_markers.add(marker)
                target = db.scalar(
                    select(CourseSession).where(CourseSession.private_description == marker).limit(1)
                )
                end_at_utc = start_at_utc + timedelta(minutes=duration_minutes)
                payload = {
                    "course_type_id": course_type.id,
                    "billing_entity_snapshot": normalize_billing_entity(course_type.billing_entity_code),
                    "snapshot_seller_legal_entity_id": course_type.seller_legal_entity_id,
                    "snapshot_payor_legal_entity_id": course_type.payor_legal_entity_id,
                    "location_id": location.id,
                    "professor_id": None,
                    "title": course_type.name,
                    "description": f"Seed local H1 2026 · {definition.key}",
                    "private_description": marker,
                    "start_at_utc": start_at_utc,
                    "end_at_utc": end_at_utc,
                    "is_all_day": False,
                    "capacity_max": capacity_max,
                    "status": SessionStatus.SCHEDULED,
                    "auto_cancel_deadline_utc": start_at_utc - timedelta(hours=12),
                    "cancel_reason": None,
                    "zoom_link": None,
                    "is_private": False,
                    "allow_online_booking": True,
                    "timezone": session_timezone,
                    "recurrence_group_id": recurrence_group_id,
                    "recurrence_rule": recurrence_rule,
                }

                if target is None:
                    db.add(
                        CourseSession(
                            **payload,
                            created_at=_utcnow(),
                            updated_at=_utcnow(),
                        )
                    )
                    created_sessions += 1
                    continue

                changed = False
                for field, value in payload.items():
                    if getattr(target, field) != value:
                        setattr(target, field, value)
                        changed = True
                if changed:
                    target.updated_at = _utcnow()
                    updated_sessions += 1
                else:
                    unchanged_sessions += 1

        obsolete_sessions = db.scalars(
            select(CourseSession).where(
                CourseSession.private_description.like(f"{SEED_PREFIX}|%"),
                CourseSession.private_description.not_in(sorted(desired_markers)),
            )
        ).all()
        for session in obsolete_sessions:
            db.delete(session)
            removed_sessions += 1

        db.commit()

    print(f"[{SEED_PREFIX}] activite_eveil_creee={created_activity}")
    print(f"[{SEED_PREFIX}] activite_eveil_mise_a_jour={updated_activity}")
    print(f"[{SEED_PREFIX}] mappings_crees={created_mappings}")
    print(f"[{SEED_PREFIX}] sessions_creees={created_sessions}")
    print(f"[{SEED_PREFIX}] sessions_mises_a_jour={updated_sessions}")
    print(f"[{SEED_PREFIX}] sessions_inchangees={unchanged_sessions}")
    print(f"[{SEED_PREFIX}] sessions_supprimees={removed_sessions}")
    for key in sorted(series_occurrence_counts):
        print(f"[{SEED_PREFIX}] serie={key} occurrences={series_occurrence_counts[key]}")


if __name__ == "__main__":
    main()
