from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.quote_planning_audit import _confirmed_variance_matches, _expected_dates


def test_confirmed_variance_only_matches_the_recorded_audit_state() -> None:
    student_id = uuid4()
    group_id = uuid4()
    payload = {
        "student_id": str(student_id),
        "series_id": str(group_id),
        "expected_sessions": 15,
        "booked_sessions": 14,
    }

    assert _confirmed_variance_matches(
        payload,
        student_id=student_id,
        group_id=group_id,
        expected_sessions=15,
        booked_sessions=14,
    )
    assert not _confirmed_variance_matches(
        payload,
        student_id=student_id,
        group_id=group_id,
        expected_sessions=15,
        booked_sessions=13,
    )
    assert not _confirmed_variance_matches(
        {**payload, "expected_sessions": "invalid"},
        student_id=student_id,
        group_id=group_id,
        expected_sessions=15,
        booked_sessions=14,
    )


def test_expected_dates_follow_the_approved_schedule_key_and_ignore_parallel_group() -> None:
    group_id = uuid4()
    selected_session_id = uuid4()
    activity_id = uuid4()
    location_id = uuid4()
    schedule_key = f"{activity_id}:primary"
    quote = SimpleNamespace(
        calendar_snapshot={
            "sessions": [
                {
                    "recommendation_key": schedule_key,
                    "activity_id": str(activity_id),
                    "location_id": str(location_id),
                    "series_key": str(group_id),
                    "date": "2026-09-09",
                    "start_time": "14:00",
                },
                {
                    "recommendation_key": schedule_key,
                    "activity_id": str(activity_id),
                    "location_id": str(location_id),
                    "series_key": str(group_id),
                    "date": "2026-09-16",
                    "start_time": "14:00",
                },
                {
                    "recommendation_key": f"{activity_id}:parallel",
                    "activity_id": str(activity_id),
                    "location_id": str(location_id),
                    "series_key": str(uuid4()),
                    "date": "2026-09-23",
                    "start_time": "14:00",
                },
            ]
        }
    )
    followup = SimpleNamespace(
        payload={
            "quote_to_enrollment": {
                "scheduleResolution": {
                    "assignedSessionByActivityId": {schedule_key: str(selected_session_id)}
                }
            }
        }
    )
    template = SimpleNamespace(
        course_type_id=activity_id,
        location_id=location_id,
        timezone="Europe/Paris",
        start_at_utc=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )

    result = _expected_dates(
        quote,
        followup,
        group_id=group_id,
        template=template,
        assigned_session_groups={selected_session_id: group_id},
    )

    assert result == {date(2026, 9, 9), date(2026, 9, 16)}


def test_expected_dates_expand_block_exclusions_from_accepted_quote() -> None:
    group_id = uuid4()
    selected_session_id = uuid4()
    activity_id = uuid4()
    location_id = uuid4()
    schedule_key = str(activity_id)
    quote = SimpleNamespace(
        calendar_snapshot={
            "blocks": [
                {
                    "recommendation_key": schedule_key,
                    "activity_id": str(activity_id),
                    "location_id": str(location_id),
                    "series_key": str(group_id),
                    "start_date": "2026-10-07",
                    "end_date": "2026-10-28",
                    "weekday": 2,
                    "start_time": "14:00",
                    "holiday_dates": ["2026-10-21", "2026-10-28"],
                }
            ]
        }
    )
    followup = SimpleNamespace(
        payload={
            "quote_to_enrollment": {
                "scheduleResolution": {
                    "assignedSessionByActivityId": {schedule_key: str(selected_session_id)}
                }
            }
        }
    )
    template = SimpleNamespace(
        course_type_id=activity_id,
        location_id=location_id,
        timezone="Europe/Paris",
        start_at_utc=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
    )

    result = _expected_dates(
        quote,
        followup,
        group_id=group_id,
        template=template,
        assigned_session_groups={selected_session_id: group_id},
    )

    assert result == {date(2026, 10, 7), date(2026, 10, 14)}
