from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.professors import list_my_internal_notes


def _rows(values):
    return SimpleNamespace(all=lambda: values)


def test_list_my_internal_notes_merges_and_sorts_session_and_student_notes() -> None:
    professor = SimpleNamespace(id=uuid4())
    location = SimpleNamespace(id=uuid4(), name="Bar-le-Duc")
    course_type = SimpleNamespace(name="Cours d'essai")
    older_session = SimpleNamespace(
        id=uuid4(),
        internal_note="Note generale",
        title="Essai piano",
        start_at_utc=datetime(2026, 7, 2, 17, 0, tzinfo=timezone.utc),
        timezone="Europe/Paris",
    )
    newer_session = SimpleNamespace(
        id=uuid4(),
        title="Essai eveil",
        start_at_utc=datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc),
        timezone="Europe/Paris",
    )
    booking = SimpleNamespace(id=uuid4(), internal_note="Tres bon contact")
    student = SimpleNamespace(id=uuid4(), first_name="Nina", last_name="Nicaise", email="nina@example.com")
    db = SimpleNamespace(
        execute=MagicMock(
            side_effect=[
                _rows([(older_session, course_type, location)]),
                _rows([(booking, newer_session, course_type, location, student)]),
            ]
        )
    )

    with (
        patch("app.api.routes.professors._resolve_professor_profile", return_value=professor),
        patch("app.api.routes.professors._resolve_professor_permissions", return_value={"can_view_planning": True}),
    ):
        notes = list_my_internal_notes(limit=20, db=db, current_user=SimpleNamespace())

    assert [note.note_type for note in notes] == ["STUDENT", "SESSION"]
    assert notes[0].student_display_name == "Nina Nicaise"
    assert notes[0].body == "Tres bon contact"
    assert notes[1].body == "Note generale"
    assert notes[1].session_timezone == "Europe/Paris"


def test_list_my_internal_notes_requires_planning_access() -> None:
    professor = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(execute=MagicMock())

    with (
        patch("app.api.routes.professors._resolve_professor_profile", return_value=professor),
        patch("app.api.routes.professors._resolve_professor_permissions", return_value={"can_view_planning": False}),
        pytest.raises(HTTPException) as exc_info,
    ):
        list_my_internal_notes(limit=20, db=db, current_user=SimpleNamespace())

    assert exc_info.value.status_code == 403
    db.execute.assert_not_called()
