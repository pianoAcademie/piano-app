from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.professors import _require_professor_session, list_my_professor_sessions
from app.models.catalog import SessionStatus


def _empty_rows():
    return SimpleNamespace(all=lambda: [])


def _list_sessions_sql(*, scope: str, permissions: dict[str, bool]) -> str:
    professor = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(execute=MagicMock(return_value=_empty_rows()))
    with (
        patch("app.api.routes.professors._resolve_professor_profile", return_value=professor),
        patch(
            "app.api.routes.professors._resolve_professor_permissions",
            return_value={"can_view_planning": True, **permissions},
        ),
    ):
        list_my_professor_sessions(
            from_=None,
            to=None,
            include_students=False,
            scope=scope,
            db=db,
            current_user=SimpleNamespace(),
        )
    return str(db.execute.call_args.args[0])


def test_professor_session_scope_defaults_to_effective_teacher_even_for_manager() -> None:
    statement = _list_sessions_sql(
        scope="mine",
        permissions={"can_view_all_school_sessions": True},
    )

    assert "WHERE course_sessions.substitute_teacher_id" in statement
    assert "AND course_sessions.professor_id" in statement


def test_professor_session_scope_all_removes_teacher_filter_for_manager() -> None:
    statement = _list_sessions_sql(
        scope="all",
        permissions={"can_view_other_teachers_sessions": True},
    )

    assert "WHERE course_sessions.substitute_teacher_id" not in statement


def test_professor_session_scope_all_falls_back_to_own_without_permission() -> None:
    statement = _list_sessions_sql(scope="all", permissions={})

    assert "WHERE course_sessions.substitute_teacher_id" in statement


def test_assigned_substitute_can_open_their_session() -> None:
    substitute_id = uuid4()
    session_obj = SimpleNamespace(professor_id=uuid4(), substitute_teacher_id=substitute_id)
    db = SimpleNamespace(scalar=MagicMock(return_value=session_obj))

    assert _require_professor_session(db, professor_id=substitute_id, session_id=uuid4()) is session_obj


def test_habitual_teacher_cannot_edit_session_while_substitute_is_assigned() -> None:
    habitual_id = uuid4()
    session_obj = SimpleNamespace(professor_id=habitual_id, substitute_teacher_id=uuid4())
    db = SimpleNamespace(scalar=MagicMock(return_value=session_obj))

    with pytest.raises(HTTPException) as exc_info:
        _require_professor_session(db, professor_id=habitual_id, session_id=uuid4())

    assert exc_info.value.status_code == 403


def test_all_scope_returns_the_effective_teacher_name() -> None:
    manager = SimpleNamespace(id=uuid4())
    habitual_id = uuid4()
    substitute_id = uuid4()
    start_at = datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc)
    session_obj = SimpleNamespace(
        id=uuid4(),
        professor_id=habitual_id,
        substitute_teacher_id=substitute_id,
        title="Cours de piano",
        description=None,
        internal_note=None,
        start_at_utc=start_at,
        end_at_utc=start_at + timedelta(hours=1),
        status=SessionStatus.SCHEDULED,
        capacity_max=1,
        zoom_link=None,
    )
    course_type = SimpleNamespace(id=uuid4(), code="PIANO", name="Piano")
    location = SimpleNamespace(id=uuid4(), code="ONLINE", name="En ligne", is_online=True)
    habitual = SimpleNamespace(id=habitual_id, first_name="Prof", last_name="Habituel")
    substitute = SimpleNamespace(id=substitute_id, first_name="Prof", last_name="Remplacant")
    db = SimpleNamespace(
        execute=MagicMock(return_value=SimpleNamespace(all=lambda: [(session_obj, course_type, location, 1)])),
        scalars=MagicMock(return_value=SimpleNamespace(all=lambda: [habitual, substitute])),
    )

    with (
        patch("app.api.routes.professors._resolve_professor_profile", return_value=manager),
        patch(
            "app.api.routes.professors._resolve_professor_permissions",
            return_value={"can_view_planning": True, "can_view_all_school_sessions": True},
        ),
    ):
        sessions = list_my_professor_sessions(
            from_=None,
            to=None,
            include_students=False,
            scope="all",
            db=db,
            current_user=SimpleNamespace(),
        )

    assert sessions[0].habitual_teacher_display_name == "Prof Habituel"
    assert sessions[0].effective_teacher_id == substitute_id
    assert sessions[0].effective_teacher_display_name == "Prof Remplacant"
