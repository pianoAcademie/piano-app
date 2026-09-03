from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import (
    _expected_activity_dates_from_snapshot,
    _expected_activity_time_window_from_snapshot,
    _load_live_series_sessions,
    _missing_dates_are_after_live_series_tail,
    _missing_expected_live_session_dates,
    _planning_session_limit_from_quote_line,
    _quote_booking_pricing_source,
    _quote_line_schedule_key,
    _quote_transform_schedule_key_candidates,
    _recover_approved_undated_solfege_expected_dates,
    _resolve_envelope_session_for_student_time,
    _resolve_scheduled_quote_transform_assignment_session,
    _validated_quote_transform_expected_dates,
)
from app.models.catalog import SessionStatus


class _FakeScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return list(self._values)


class _FakeSession:
    def __init__(self, values: list[object]) -> None:
        self._values = values
        self.scalar_calls = 0

    def scalars(self, _statement) -> _FakeScalarResult:
        self.scalar_calls += 1
        return _FakeScalarResult(self._values)


class _FakeSequentialSession:
    def __init__(self, responses: list[list[object]]) -> None:
        self._responses = responses
        self.scalar_calls = 0

    def scalars(self, _statement) -> _FakeScalarResult:
        index = min(self.scalar_calls, len(self._responses) - 1)
        self.scalar_calls += 1
        return _FakeScalarResult(self._responses[index])


class _FakeEnvelopeSession:
    def __init__(self, course_type: object, sessions: list[object]) -> None:
        self._course_type = course_type
        self._sessions = sessions

    def scalar(self, _statement) -> object:
        return self._course_type

    def scalars(self, _statement) -> _FakeScalarResult:
        return _FakeScalarResult(self._sessions)


class _FakeSolfegeRecoverySession:
    def __init__(self, course_type: object, location: object, sessions: list[object]) -> None:
        self._scalar_values = [course_type, location]
        self._sessions = sessions

    def scalar(self, _statement) -> object:
        return self._scalar_values.pop(0)

    def scalars(self, _statement) -> _FakeScalarResult:
        return _FakeScalarResult(self._sessions)


def _session(
    *,
    session_id: str,
    course_type_id,
    location_id,
    start_at_utc: datetime,
    end_at_utc: datetime,
    recurrence_group_id=None,
    status=SessionStatus.SCHEDULED,
):
    return SimpleNamespace(
        id=session_id,
        course_type_id=course_type_id,
        location_id=location_id,
        start_at_utc=start_at_utc,
        end_at_utc=end_at_utc,
        recurrence_group_id=recurrence_group_id,
        timezone="Europe/Paris",
        status=status,
    )


class QuoteLiveSeriesMatchingTests(unittest.TestCase):
    def test_quote_booking_pricing_source_is_bounded_and_keeps_duplicate_line_identity(self) -> None:
        quote_id = uuid4()
        first_line_id = uuid4()
        second_line_id = uuid4()

        first_source = _quote_booking_pricing_source(
            quote_id=quote_id,
            quote_service_lines=[SimpleNamespace(id=first_line_id)],
        )
        second_source = _quote_booking_pricing_source(
            quote_id=quote_id,
            quote_service_lines=[SimpleNamespace(id=second_line_id)],
        )

        self.assertLessEqual(len(first_source), 120)
        self.assertNotEqual(first_source, second_source)
        self.assertIn(str(first_line_id), first_source)

    def test_recovers_legacy_undated_solfege_from_exact_approved_series(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        recurrence_id = uuid4()
        sessions = [
            _session(
                session_id=str(uuid4()),
                course_type_id=activity_id,
                location_id=location_id,
                start_at_utc=datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc) + timedelta(weeks=index),
                end_at_utc=datetime(2026, 10, 1, 17, 45, tzinfo=timezone.utc) + timedelta(weeks=index),
                recurrence_group_id=recurrence_id,
            )
            for index in range(26)
        ]
        quote = SimpleNamespace(
            school_year_label="2026-2027",
            selected_solfege_slot={
                "weekday": 3,
                "start_time": "19:00",
                "end_time": "19:45",
                "location_id": str(location_id),
            },
            calendar_snapshot={
                "blocks": [{"activity_id": str(activity_id), "activity_label": "Solfège niveau 4"}],
                "sessions": [],
            },
        )
        db = _FakeSolfegeRecoverySession(
            SimpleNamespace(mode="ONLINE"),
            SimpleNamespace(name="Online", timezone="Europe/Paris"),
            sessions,
        )

        recovered = _recover_approved_undated_solfege_expected_dates(
            db,
            quote=quote,
            activity_id=activity_id,
            selected_session=sessions[0],
            session_limit=26,
        )

        self.assertEqual(len(recovered), 26)
        self.assertEqual(recovered[0], date(2026, 10, 1))

    def test_does_not_recover_undated_solfege_when_approved_slot_differs(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        recurrence_id = uuid4()
        sessions = [
            _session(
                session_id=str(uuid4()),
                course_type_id=activity_id,
                location_id=location_id,
                start_at_utc=datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc) + timedelta(weeks=index),
                end_at_utc=datetime(2026, 10, 1, 17, 45, tzinfo=timezone.utc) + timedelta(weeks=index),
                recurrence_group_id=recurrence_id,
            )
            for index in range(26)
        ]
        quote = SimpleNamespace(
            school_year_label="2026-2027",
            selected_solfege_slot={
                "weekday": 0,
                "start_time": "18:50",
                "end_time": "19:35",
                "location_id": str(location_id),
            },
            calendar_snapshot={
                "blocks": [{"activity_id": str(activity_id), "activity_label": "Solfège niveau 4"}],
                "sessions": [],
            },
        )
        db = _FakeSolfegeRecoverySession(
            SimpleNamespace(mode="ONLINE"),
            SimpleNamespace(name="Online", timezone="Europe/Paris"),
            sessions,
        )

        self.assertEqual(
            _recover_approved_undated_solfege_expected_dates(
                db,
                quote=quote,
                activity_id=activity_id,
                selected_session=sessions[0],
                session_limit=26,
            ),
            [],
        )

    def test_expected_dates_fall_back_to_planning_blocks(self) -> None:
        activity_id = uuid4()
        quote = SimpleNamespace(
            calendar_snapshot={
                "sessions": [],
                "blocks": [
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": f"{activity_id}:main",
                        "start_date": "2026-09-08",
                        "end_date": "2026-09-29",
                        "weekday": 1,
                        "start_time": "12:00",
                        "end_time": "13:00",
                        "holiday_dates": ["2026-09-22"],
                    }
                ],
            }
        )

        self.assertEqual(
            _expected_activity_dates_from_snapshot(
                quote,
                activity_id=activity_id,
                schedule_key=f"{activity_id}:main",
            ),
            [date(2026, 9, 8), date(2026, 9, 15), date(2026, 9, 29)],
        )

    def test_expected_dates_prefer_filtered_sessions_over_theoretical_block(self) -> None:
        activity_id = uuid4()
        quote = SimpleNamespace(
            calendar_snapshot={
                "sessions": [
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": f"{activity_id}:main",
                        "date": "2026-10-07",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": f"{activity_id}:main",
                        "date": "2026-10-14",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": f"{activity_id}:main",
                        "date": "2026-11-04",
                    },
                ],
                "blocks": [
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": f"{activity_id}:main",
                        "start_date": "2026-10-07",
                        "end_date": "2026-11-04",
                        "weekday": 2,
                        "start_time": "17:00",
                        "end_time": "18:00",
                    }
                ],
            }
        )

        self.assertEqual(
            _expected_activity_dates_from_snapshot(
                quote,
                activity_id=activity_id,
                schedule_key=f"{activity_id}:main",
            ),
            [date(2026, 10, 7), date(2026, 10, 14), date(2026, 11, 4)],
        )
        self.assertEqual(
            _expected_activity_dates_from_snapshot(
                quote,
                activity_id=activity_id,
                schedule_key=f"{activity_id}:main",
                prefer_blocks=True,
            ),
            [date(2026, 10, 7), date(2026, 10, 14), date(2026, 10, 21), date(2026, 10, 28), date(2026, 11, 4)],
        )

    def test_expected_dates_keep_selected_series_when_duplicate_keys_are_shared(self) -> None:
        activity_id = uuid4()
        tuesday_series_id = uuid4()
        friday_series_id = uuid4()
        schedule_key = f"{activity_id}:second_piano_course"
        quote = SimpleNamespace(
            calendar_snapshot={
                "sessions": [
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(tuesday_series_id),
                        "date": "2026-09-08",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(tuesday_series_id),
                        "date": "2026-09-15",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(friday_series_id),
                        "date": "2026-09-11",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(friday_series_id),
                        "date": "2026-09-18",
                    },
                ],
                "blocks": [],
            }
        )

        self.assertEqual(
            _expected_activity_dates_from_snapshot(
                quote,
                activity_id=activity_id,
                schedule_key=schedule_key,
                expected_series_key=str(friday_series_id),
                expected_weekday=4,
            ),
            [date(2026, 9, 11), date(2026, 9, 18)],
        )

    def test_expected_dates_fall_back_to_selected_series_when_line_key_is_missing(self) -> None:
        activity_id = uuid4()
        tuesday_series_id = uuid4()
        friday_series_id = uuid4()
        shared_schedule_key = f"{activity_id}:second_piano_course"
        historical_line_key = f"{activity_id}:line:{uuid4()}"
        quote = SimpleNamespace(
            calendar_snapshot={
                "sessions": [
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": shared_schedule_key,
                        "series_key": str(tuesday_series_id),
                        "date": "2026-09-08",
                        "start_time": "16:00",
                        "end_time": "17:00",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": shared_schedule_key,
                        "series_key": str(tuesday_series_id),
                        "date": "2026-09-15",
                        "start_time": "16:00",
                        "end_time": "17:00",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": shared_schedule_key,
                        "series_key": str(friday_series_id),
                        "date": "2026-09-11",
                        "start_time": "16:00",
                        "end_time": "17:00",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": shared_schedule_key,
                        "series_key": str(friday_series_id),
                        "date": "2026-09-18",
                        "start_time": "16:00",
                        "end_time": "17:00",
                    },
                ],
                "blocks": [],
            }
        )

        self.assertEqual(
            _expected_activity_dates_from_snapshot(
                quote,
                activity_id=activity_id,
                schedule_key=historical_line_key,
                expected_series_key=str(friday_series_id),
                expected_weekday=4,
            ),
            [date(2026, 9, 11), date(2026, 9, 18)],
        )
        self.assertEqual(
            _expected_activity_time_window_from_snapshot(
                quote,
                activity_id=activity_id,
                schedule_key=historical_line_key,
                expected_series_key=str(friday_series_id),
                expected_weekday=4,
            ),
            ("16:00", "17:00"),
        )

    def test_expected_dates_accept_live_activity_alias_from_recommendation_key(self) -> None:
        billed_activity_id = uuid4()
        live_activity_id = uuid4()
        series_id = uuid4()
        schedule_key = str(billed_activity_id)
        quote = SimpleNamespace(
            calendar_snapshot={
                "sessions": [
                    {
                        "activity_id": str(live_activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(series_id),
                        "date": "2026-09-11",
                        "start_time": "17:00",
                        "end_time": "18:00",
                    },
                    {
                        "activity_id": str(live_activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(series_id),
                        "date": "2026-09-18",
                        "start_time": "17:00",
                        "end_time": "18:00",
                    },
                ],
                "blocks": [
                    {
                        "activity_id": str(live_activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(series_id),
                        "start_date": "2026-09-11",
                        "end_date": "2026-09-18",
                        "weekday": 4,
                        "start_time": "17:00",
                        "end_time": "18:00",
                    }
                ],
            }
        )

        self.assertEqual(
            _expected_activity_dates_from_snapshot(
                quote,
                activity_id=billed_activity_id,
                schedule_key=schedule_key,
                expected_series_key=str(series_id),
                expected_weekday=4,
            ),
            [date(2026, 9, 11), date(2026, 9, 18)],
        )
        self.assertEqual(
            _expected_activity_time_window_from_snapshot(
                quote,
                activity_id=billed_activity_id,
                schedule_key=schedule_key,
                expected_series_key=str(series_id),
                expected_weekday=4,
            ),
            ("17:00", "18:00"),
        )

    def test_expected_dates_keep_selected_block_series_when_duplicate_keys_are_shared(self) -> None:
        activity_id = uuid4()
        tuesday_series_id = uuid4()
        friday_series_id = uuid4()
        schedule_key = f"{activity_id}:second_piano_course"
        quote = SimpleNamespace(
            calendar_snapshot={
                "sessions": [],
                "blocks": [
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(tuesday_series_id),
                        "start_date": "2026-09-08",
                        "end_date": "2026-09-22",
                        "weekday": 1,
                        "start_time": "16:00",
                        "end_time": "17:00",
                    },
                    {
                        "activity_id": str(activity_id),
                        "recommendation_key": schedule_key,
                        "series_key": str(friday_series_id),
                        "start_date": "2026-09-11",
                        "end_date": "2026-09-25",
                        "weekday": 4,
                        "start_time": "16:00",
                        "end_time": "17:00",
                    },
                ],
            }
        )

        self.assertEqual(
            _expected_activity_dates_from_snapshot(
                quote,
                activity_id=activity_id,
                schedule_key=schedule_key,
                expected_series_key=str(friday_series_id),
                expected_weekday=4,
            ),
            [date(2026, 9, 11), date(2026, 9, 18), date(2026, 9, 25)],
        )

    def test_student_time_resolves_to_teacher_envelope_session(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        selected_exact = _session(
            session_id="selected-exact",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc),
        )
        teacher_envelope = _session(
            session_id="teacher-envelope",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 8, 9, 45, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc),
        )
        db = _FakeEnvelopeSession(
            SimpleNamespace(supports_student_time_overrides=True),
            [selected_exact, teacher_envelope],
        )

        resolved = _resolve_envelope_session_for_student_time(
            db,
            selected_session=selected_exact,
            student_start_time_local="12:00",
            student_end_time_local="13:00",
        )

        self.assertEqual(resolved.id, "teacher-envelope")

    def test_quote_line_schedule_key_keeps_automatic_line_source(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            activity_id=activity_id,
            meta={"typeform_automatic_line": "adult_collective_main"},
        )

        self.assertEqual(_quote_line_schedule_key(line), f"{activity_id}:adult_collective_main")

    def test_transform_schedule_key_candidates_include_historical_quote_line_key(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            id=uuid4(),
            activity_id=activity_id,
            meta={"recommendation_key": f"{activity_id}:historical"},
        )

        self.assertEqual(
            _quote_transform_schedule_key_candidates(
                f"{activity_id}:snapshot",
                activity_id=activity_id,
                quote_service_lines=[line],
            ),
            [f"{activity_id}:snapshot", f"{activity_id}:historical", str(activity_id)],
        )

    def test_transform_schedule_key_candidates_include_solfege_snapshot_alias(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(id=uuid4(), activity_id=activity_id, meta={})
        snapshot_key = f"{activity_id}:online_solfege"

        self.assertEqual(
            _quote_transform_schedule_key_candidates(
                str(activity_id),
                activity_id=activity_id,
                quote_service_lines=[line],
                calendar_snapshot={
                    "blocks": [
                        {
                            "activity_id": str(activity_id),
                            "recommendation_key": snapshot_key,
                        }
                    ]
                },
            ),
            [str(activity_id), snapshot_key],
        )

    def test_completed_occurrence_recovers_scheduled_representative_from_same_series(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        recurrence_group_id = uuid4()
        completed = _session(
            session_id="completed",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 2, 17, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
            status=SessionStatus.COMPLETED,
        )
        scheduled = _session(
            session_id="scheduled",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 9, 17, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        wrong_time = _session(
            session_id="wrong-time",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 9, 17, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        db = _FakeSession([scheduled, wrong_time])

        resolved = _resolve_scheduled_quote_transform_assignment_session(
            db,
            activity_id=course_type_id,
            selected_session=completed,
            series_assignment={},
            expected_dates=[date(2026, 9, 2), date(2026, 9, 9)],
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, "scheduled")

    def test_missing_occurrence_recovers_series_from_stable_assignment_metadata(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        recurrence_group_id = uuid4()
        scheduled = _session(
            session_id="scheduled",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 9, 16, 5, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 9, 16, 35, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        db = _FakeSession([scheduled])

        resolved = _resolve_scheduled_quote_transform_assignment_session(
            db,
            activity_id=course_type_id,
            selected_session=None,
            series_assignment={
                "recurrenceGroupId": str(recurrence_group_id),
                "courseTypeId": str(course_type_id),
                "locationId": str(location_id),
                "timezone": "Europe/Paris",
                "localWeekday": 2,
                "localStartTime": "18:05",
                "localEndTime": "18:35",
            },
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, "scheduled")

    def test_scheduled_occurrence_with_wrong_activity_is_not_accepted(self) -> None:
        course_type_id = uuid4()
        wrong_course_type_id = uuid4()
        location_id = uuid4()
        selected = _session(
            session_id="wrong-activity",
            course_type_id=wrong_course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 9, 16, 5, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 9, 16, 35, tzinfo=timezone.utc),
        )
        correct = _session(
            session_id="correct-activity",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 9, 16, 5, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 9, 16, 35, tzinfo=timezone.utc),
        )
        db = _FakeSession([correct])

        resolved = _resolve_scheduled_quote_transform_assignment_session(
            db,
            activity_id=course_type_id,
            selected_session=selected,
            series_assignment={},
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, "correct-activity")

    def test_planning_session_limit_reads_top_level_or_template_meta(self) -> None:
        top_level_line = SimpleNamespace(
            meta={
                "planning_session_limit": "10",
                "typeform_template": {"planning_session_limit": 32},
            },
        )
        template_line = SimpleNamespace(
            meta={
                "typeform_template": {"planning_session_limit": "10"},
            },
        )
        invalid_line = SimpleNamespace(
            meta={
                "planning_session_limit": "0",
            },
        )

        self.assertEqual(_planning_session_limit_from_quote_line(top_level_line), 10)
        self.assertEqual(_planning_session_limit_from_quote_line(template_line), 10)
        self.assertIsNone(_planning_session_limit_from_quote_line(invalid_line))

    def test_planning_session_limit_can_use_the_approved_service_quantity(self) -> None:
        line = SimpleNamespace(
            meta={},
            pricing_unit="session",
            quantity="31.00",
        )

        self.assertEqual(
            _planning_session_limit_from_quote_line(line, allow_session_quantity=True),
            31,
        )

    def test_detached_first_occurrence_recovers_full_series_from_expected_dates(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        recurrence_group_id = uuid4()
        selected = _session(
            session_id="selected",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=None,
        )
        saturday_2 = _session(
            session_id="sat-2",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        saturday_3 = _session(
            session_id="sat-3",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        wrong_time = _session(
            session_id="wrong-time",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        wrong_activity = _session(
            session_id="wrong-activity",
            course_type_id=uuid4(),
            location_id=location_id,
            start_at_utc=datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=uuid4(),
        )
        db = _FakeSession([selected, saturday_2, saturday_3, wrong_time, wrong_activity])

        rows = _load_live_series_sessions(
            db,
            selected_session=selected,
            expected_dates=[
                date(2026, 9, 19),
                date(2026, 9, 26),
                date(2026, 10, 3),
            ],
        )

        self.assertEqual(db.scalar_calls, 1)
        self.assertEqual([row.id for row in rows], ["selected", "sat-2", "sat-3"])

    def test_recurrence_group_falls_back_to_signature_when_series_was_regenerated(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        original_group_id = uuid4()
        regenerated_group_id = uuid4()
        selected = _session(
            session_id="selected",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=original_group_id,
        )
        regenerated_2 = _session(
            session_id="regen-2",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        regenerated_3 = _session(
            session_id="regen-3",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        wrong_time = _session(
            session_id="wrong-time",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        db = _FakeSequentialSession([
            [selected],
            [selected, regenerated_2, regenerated_3, wrong_time],
        ])

        rows = _load_live_series_sessions(
            db,
            selected_session=selected,
            expected_dates=[
                date(2026, 9, 19),
                date(2026, 9, 26),
                date(2026, 10, 3),
            ],
        )

        self.assertEqual(db.scalar_calls, 2)
        self.assertEqual([row.id for row in rows], ["selected", "regen-2", "regen-3"])

    def test_recurrence_group_fallback_keeps_selected_weekday(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        original_group_id = uuid4()
        regenerated_group_id = uuid4()
        selected = _session(
            session_id="selected",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc),
            recurrence_group_id=original_group_id,
        )
        monday_2 = _session(
            session_id="monday-2",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        tuesday_same_time = _session(
            session_id="tuesday-same-time",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        wednesday_same_time = _session(
            session_id="wednesday-same-time",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        db = _FakeSequentialSession([
            [selected],
            [selected, monday_2, tuesday_same_time, wednesday_same_time],
        ])

        rows = _load_live_series_sessions(
            db,
            selected_session=selected,
            expected_dates=[
                date(2026, 9, 7),
                date(2026, 9, 14),
            ],
        )

        self.assertEqual(db.scalar_calls, 2)
        self.assertEqual([row.id for row in rows], ["selected", "monday-2"])

    def test_recurrence_group_fallback_accepts_envelope_sessions_for_student_time(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        original_group_id = uuid4()
        regenerated_group_id = uuid4()
        selected = _session(
            session_id="selected",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 11, 16, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 11, 17, 0, tzinfo=timezone.utc),
            recurrence_group_id=original_group_id,
        )
        envelope_2 = _session(
            session_id="envelope-2",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 18, 18, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        envelope_3 = _session(
            session_id="envelope-3",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        wrong_envelope = _session(
            session_id="wrong-envelope",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc),
            recurrence_group_id=regenerated_group_id,
        )
        db = _FakeSequentialSession([
            [selected],
            [selected, envelope_2, envelope_3, wrong_envelope],
        ])

        rows = _load_live_series_sessions(
            db,
            selected_session=selected,
            expected_dates=[
                date(2026, 9, 11),
                date(2026, 9, 18),
                date(2026, 9, 25),
            ],
            student_start_time_local="18:00",
            student_end_time_local="19:00",
        )

        self.assertEqual(db.scalar_calls, 2)
        self.assertEqual([row.id for row in rows], ["selected", "envelope-2", "envelope-3"])

    def test_recurrence_group_fallback_keeps_only_expected_dates(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        recurrence_group_id = uuid4()
        selected = _session(
            session_id="selected",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        current_2 = _session(
            session_id="current-2",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        current_3 = _session(
            session_id="current-3",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        db = _FakeSequentialSession([
            [selected, current_2, current_3],
            [selected, current_2, current_3],
        ])

        rows = _load_live_series_sessions(
            db,
            selected_session=selected,
            expected_dates=[
                date(2026, 9, 19),
                date(2026, 9, 26),
                date(2026, 10, 3),
                date(2026, 10, 10),
            ],
        )

        self.assertEqual(db.scalar_calls, 2)
        self.assertEqual([row.id for row in rows], ["selected", "current-2", "current-3"])

    def test_recurrence_group_fallback_does_not_fill_missing_expected_dates_with_holidays(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        recurrence_group_id = uuid4()
        selected = _session(
            session_id="selected",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2027, 3, 31, 9, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2027, 3, 31, 10, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        holiday = _session(
            session_id="holiday",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2027, 4, 7, 9, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2027, 4, 7, 10, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        expected_after_holiday = _session(
            session_id="expected-after-holiday",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2027, 4, 21, 9, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2027, 4, 21, 10, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        db = _FakeSequentialSession([
            [selected, holiday, expected_after_holiday],
            [selected, holiday, expected_after_holiday],
        ])

        rows = _load_live_series_sessions(
            db,
            selected_session=selected,
            expected_dates=[
                date(2027, 3, 31),
                date(2027, 4, 21),
                date(2027, 4, 28),
            ],
        )

        self.assertEqual(db.scalar_calls, 2)
        self.assertEqual([row.id for row in rows], ["selected", "expected-after-holiday"])
        self.assertEqual(
            _missing_expected_live_session_dates(
                expected_dates=[
                    date(2027, 3, 31),
                    date(2027, 4, 21),
                    date(2027, 4, 28),
                ],
                live_sessions=rows,
            ),
            [date(2027, 4, 28)],
        )

    def test_tail_only_missing_dates_are_treated_as_legacy_theoretical_overrun(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        recurrence_group_id = uuid4()
        live_1 = _session(
            session_id="live-1",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2027, 4, 6, 7, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2027, 4, 6, 8, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        live_2 = _session(
            session_id="live-2",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2027, 4, 13, 7, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2027, 4, 13, 8, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )

        self.assertTrue(
            _missing_dates_are_after_live_series_tail(
                missing_dates=[date(2027, 5, 4), date(2027, 5, 11)],
                live_sessions=[live_1, live_2],
            )
        )
        self.assertFalse(
            _missing_dates_are_after_live_series_tail(
                missing_dates=[date(2027, 4, 7), date(2027, 5, 4)],
                live_sessions=[live_1, live_2],
            )
        )

    def test_transform_rejects_an_approved_snapshot_shorter_than_the_billed_quantity(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _validated_quote_transform_expected_dates(
                [date(2026, 9, 14)] * 13,
                session_limit=31,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("13 séances du devis sont reliées", str(raised.exception.detail))
        self.assertIn("31 séances facturées", str(raised.exception.detail))
        self.assertIn("étape 3", str(raised.exception.detail))

    def test_unmatched_series_explains_that_approved_dates_still_exist(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _validated_quote_transform_expected_dates([], session_limit=32, approved_dates_count=32)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("le devis contient bien 32 séances", str(raised.exception.detail))
        self.assertIn("aucune n’est reliée", str(raised.exception.detail))
        self.assertIn("sans modifier les dates ni les montants", str(raised.exception.detail))

    def test_empty_planning_does_not_claim_approved_dates_exist(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _validated_quote_transform_expected_dates([], session_limit=32, approved_dates_count=0)
        self.assertIn("0 séances du devis sont reliées", str(raised.exception.detail))
        self.assertNotIn("contient bien", str(raised.exception.detail))

    def test_transform_keeps_the_full_approved_session_quantity(self) -> None:
        approved_dates = [date(2026, 9, 1) + timedelta(days=index * 7) for index in range(31)]

        self.assertEqual(
            _validated_quote_transform_expected_dates(approved_dates, session_limit=31),
            approved_dates,
        )

    def test_deduplicates_live_sessions_with_same_local_slot(self) -> None:
        course_type_id = uuid4()
        location_id = uuid4()
        recurrence_group_id = uuid4()
        selected = _session(
            session_id="selected",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        duplicate_same_slot = _session(
            session_id="duplicate",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        next_week = _session(
            session_id="next-week",
            course_type_id=course_type_id,
            location_id=location_id,
            start_at_utc=datetime(2026, 9, 23, 14, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 23, 15, 0, tzinfo=timezone.utc),
            recurrence_group_id=recurrence_group_id,
        )
        db = _FakeSession([duplicate_same_slot, selected, next_week])

        rows = _load_live_series_sessions(
            db,
            selected_session=selected,
            expected_dates=[
                date(2026, 9, 16),
                date(2026, 9, 23),
            ],
        )

        self.assertEqual([row.id for row in rows], ["selected", "next-week"])


if __name__ == "__main__":
    unittest.main()
