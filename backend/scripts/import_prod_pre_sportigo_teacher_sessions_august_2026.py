from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.payout import PayoutStatus, ProfessorSessionPayout
from app.services.invoice_documents import normalize_billing_entity
from app.services.payouts import resolve_hourly_rate_for_missing_service
from app.services.session_teachers import replace_session_professors

SOURCE_FILE = "coach_20260801-20260831.csv"
MARKER_PREFIX = "PRE_SPORTIGO_COACH_AUGUST_2026"
COURSE_CODE = "PIANO_GROUP_ONSITE_1H"
LOCATION_CODE = "RICHELIEU"
PARIS = ZoneInfo("Europe/Paris")


@dataclass(frozen=True)
class HistoricalSession:
    local_start: datetime
    professor_name: str
    registered_count: int
    participant_count: int

    @property
    def effective_headcount(self) -> int:
        return self.participant_count if self.participant_count > 0 else self.registered_count

    @property
    def marker(self) -> str:
        professor_key = _normalized(self.professor_name).replace(" ", "-").upper()
        return f"{MARKER_PREFIX}|{self.local_start:%Y-%m-%dT%H:%M}|{professor_key}"


# Gayane Nersisyan is intentionally excluded at the user's request.
ROWS = (
    HistoricalSession(datetime(2026, 8, 4, 12, 0), "PAISHAO CHENG", 3, 3),
    HistoricalSession(datetime(2026, 8, 4, 19, 0), "PAISHAO CHENG", 7, 7),
    HistoricalSession(datetime(2026, 8, 5, 19, 0), "PAISHAO CHENG", 7, 7),
    HistoricalSession(datetime(2026, 8, 6, 19, 0), "RUDY GATTI", 6, 0),
    HistoricalSession(datetime(2026, 8, 7, 19, 0), "PAISHAO CHENG", 4, 4),
)


def _normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    return " ".join("".join(char for char in folded if not unicodedata.combining(char)).casefold().split())


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _find_professor(professors: list[Professor], name: str) -> Professor:
    expected = _normalized(name)
    matches = [
        row
        for row in professors
        if _normalized(f"{row.first_name or ''} {row.last_name or ''}") == expected
    ]
    if len(matches) != 1:
        labels = [f"{row.first_name} {row.last_name} ({row.id})" for row in matches]
        raise RuntimeError(f"Expected exactly one professor for {name!r}; found {len(matches)}: {labels}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Import pre-Sportigo August 2026 teacher sessions into production.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is a dry-run.")
    args = parser.parse_args()
    summary = Counter()

    with SessionLocal() as db:
        course_type = db.scalar(
            select(CourseType).where(CourseType.code == COURSE_CODE, CourseType.active.is_(True)).limit(1)
        )
        if course_type is None:
            raise RuntimeError(f"Missing active course type {COURSE_CODE}")
        if course_type.payor_legal_entity_id is None or course_type.seller_legal_entity_id is None:
            raise RuntimeError(f"Course type {COURSE_CODE} has incomplete legal-entity configuration")

        location = db.scalar(
            select(Location).where(Location.code == LOCATION_CODE, Location.active.is_(True)).limit(1)
        )
        if location is None:
            raise RuntimeError(f"Missing active location {LOCATION_CODE}")

        professors = db.scalars(select(Professor)).all()
        resolved_professors = {
            row.professor_name: _find_professor(professors, row.professor_name)
            for row in ROWS
        }

        print(
            f"[{MARKER_PREFIX}] source={SOURCE_FILE} mode={'APPLY' if args.apply else 'DRY_RUN'} "
            f"course={course_type.code}:{course_type.name} location={location.code}:{location.name}"
        )

        for row in ROWS:
            professor = resolved_professors[row.professor_name]
            start_at_utc = row.local_start.replace(tzinfo=PARIS).astimezone(ZoneInfo("UTC"))
            end_at_utc = start_at_utc + timedelta(minutes=60)
            existing = db.scalars(
                select(CourseSession).where(
                    CourseSession.course_type_id == course_type.id,
                    CourseSession.location_id == location.id,
                    CourseSession.start_at_utc == start_at_utc,
                    CourseSession.end_at_utc == end_at_utc,
                )
            ).all()
            if len(existing) > 1:
                raise RuntimeError(f"Ambiguous existing sessions for {row.local_start.isoformat()}: {len(existing)}")

            session_obj = existing[0] if existing else None
            if session_obj is not None and session_obj.professor_id not in (None, professor.id):
                raise RuntimeError(
                    f"Existing session {session_obj.id} at {row.local_start.isoformat()} belongs to another professor"
                )

            resolved_rate = resolve_hourly_rate_for_missing_service(
                db,
                professor_id=professor.id,
                course_type_id=course_type.id,
                location_id=location.id,
                on_date=row.local_start.date(),
                attendees_count=row.effective_headcount,
            )
            if resolved_rate is None:
                raise RuntimeError(
                    f"No teacher rate for {row.professor_name} on {row.local_start.date()} "
                    f"with headcount={row.effective_headcount}"
                )
            rate = _money(Decimal(resolved_rate.hourly_rate))

            if session_obj is None:
                summary["sessions_to_create" if not args.apply else "sessions_created"] += 1
                session_obj = CourseSession(
                    course_type_id=course_type.id,
                    billing_entity_snapshot=normalize_billing_entity(course_type.billing_entity_code),
                    snapshot_seller_legal_entity_id=course_type.seller_legal_entity_id,
                    snapshot_payor_legal_entity_id=course_type.payor_legal_entity_id,
                    location_id=location.id,
                    professor_id=professor.id,
                    title=course_type.name,
                    description="Cours donne avant la migration Sportigo",
                    private_description=row.marker,
                    internal_note=(
                        f"Import {SOURCE_FILE}; inscrits={row.registered_count}; "
                        f"participants_saisis={row.participant_count}; "
                        f"effectif_tarif={row.effective_headcount}."
                    ),
                    start_at_utc=start_at_utc,
                    end_at_utc=end_at_utc,
                    is_all_day=False,
                    capacity_max=max(int(course_type.default_capacity or 0), row.registered_count),
                    status=SessionStatus.COMPLETED,
                    auto_cancel_deadline_utc=start_at_utc - timedelta(hours=12),
                    auto_cancel_rule_enabled_override=False,
                    auto_cancel_checked_at=start_at_utc,
                    is_private=True,
                    allow_online_booking=False,
                    visibility_scope="PRIVATE",
                    booking_scope="PRIVATE",
                    timezone=location.timezone or "Europe/Paris",
                )
                if args.apply:
                    db.add(session_obj)
                    db.flush()
                    replace_session_professors(db, session_obj=session_obj, professor_ids=[professor.id])
            else:
                summary["sessions_existing"] += 1
                if session_obj.professor_id is None:
                    summary["assignments_to_add" if not args.apply else "assignments_added"] += 1
                    if args.apply:
                        replace_session_professors(db, session_obj=session_obj, professor_ids=[professor.id])

            payout = None
            if session_obj.id is not None:
                payout = db.scalar(
                    select(ProfessorSessionPayout).where(
                        ProfessorSessionPayout.session_id == session_obj.id,
                        ProfessorSessionPayout.professor_id == professor.id,
                    )
                )
            if payout is None:
                summary["payouts_to_create" if not args.apply else "payouts_created"] += 1
                if args.apply:
                    db.add(
                        ProfessorSessionPayout(
                            session_id=session_obj.id,
                            professor_id=professor.id,
                            duration_hours=Decimal("1.00"),
                            hourly_rate_snapshot=rate,
                            currency_snapshot=(resolved_rate.currency_code or "EUR")[:3].upper(),
                            amount_snapshot=rate,
                            payout_status=PayoutStatus.PENDING,
                        )
                    )
            else:
                summary["payouts_existing"] += 1
                if _money(Decimal(payout.amount_snapshot)) != rate:
                    raise RuntimeError(
                        f"Existing payout mismatch for session {session_obj.id}: "
                        f"stored={payout.amount_snapshot} expected={rate}"
                    )

            fallback_note = " (participants=0, fallback inscrits)" if row.participant_count == 0 else ""
            print(
                f"[{MARKER_PREFIX}] row={row.local_start:%Y-%m-%d %H:%M} professor={row.professor_name} "
                f"registered={row.registered_count} participants={row.participant_count} "
                f"rate_headcount={row.effective_headcount}{fallback_note} hourly_rate={rate} "
                f"session={'existing' if existing else 'create'} payout={'existing' if payout else 'create'}"
            )

        if args.apply:
            db.commit()
        else:
            db.rollback()

    for key in sorted(summary):
        print(f"[{MARKER_PREFIX}] {key}={summary[key]}")
    print(f"[{MARKER_PREFIX}] gayane_excluded=1")


if __name__ == "__main__":
    main()
