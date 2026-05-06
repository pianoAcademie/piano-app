from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _load_live_series_sessions


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


def _session(
    *,
    session_id: str,
    course_type_id,
    location_id,
    start_at_utc: datetime,
    end_at_utc: datetime,
    recurrence_group_id=None,
):
    return SimpleNamespace(
        id=session_id,
        course_type_id=course_type_id,
        location_id=location_id,
        start_at_utc=start_at_utc,
        end_at_utc=end_at_utc,
        recurrence_group_id=recurrence_group_id,
        timezone="Europe/Paris",
    )


class QuoteLiveSeriesMatchingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
