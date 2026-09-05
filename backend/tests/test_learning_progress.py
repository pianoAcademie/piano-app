from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.learning_progress import apply_learning_change, initial_learning_state
from app.api.routes.repertoire import LearningChange, professor_change_learning, _require_learning_access

CATALOG = {"book": ["one", "two", "three"], "next": ["four"], "empty": []}


def change(state, action, **kwargs):
    return apply_learning_change(state, action=action, product_id=kwargs.get("product_id"),
        piece_id=kwargs.get("piece_id"), statuses=kwargs.get("statuses"), catalog=CATALOG,
        session_id="lesson", now=datetime(2026, 9, 5, 15, tzinfo=timezone.utc))


def current():
    return {"product_id": "book", "books": {"book": {"pieces": {}, "current_piece_id": "two", "completed": False}}}


def test_reenrollment_does_not_infer_completed_pieces_or_dates():
    state = initial_learning_state([SimpleNamespace(product_id="book", current_piece_id="two", status="IN_PROGRESS")])
    expected = current()
    expected["books"]["book"]["note"] = ""
    assert state == expected


def test_initial_state_preserves_existing_teacher_note():
    state = initial_learning_state([SimpleNamespace(product_id="book", current_piece_id="two", status="IN_PROGRESS", internal_note="Revoir la main gauche")])
    assert state["books"]["book"]["note"] == "Revoir la main gauche"


def test_initial_pending_delivery_does_not_become_current_automatically():
    state = initial_learning_state([SimpleNamespace(product_id="book", current_piece_id=None, status="TO_DELIVER")])
    assert state["product_id"] is None


def test_arbitrary_baseline_with_skips_and_review_has_no_completion_date():
    state = change(current(), "HISTORY", product_id="book", piece_id="two", statuses={"one": "REVIEW", "three": "COMPLETED"})
    assert state["books"]["book"]["pieces"]["three"] == {"status": "COMPLETED", "source": "BASELINE", "completed_at": None}
    assert state["books"]["book"]["pieces"]["one"]["status"] == "REVIEW"
    assert "two" not in state["books"]["book"]["pieces"]


def test_completion_selects_earlier_piece_and_preserves_unknowns():
    state = current()
    before = deepcopy(state)
    after = change(state, "COMPLETE_PIECE", piece_id="one")
    assert state == before
    assert after["books"]["book"]["current_piece_id"] == "one"
    assert after["books"]["book"]["pieces"]["two"]["session_id"] == "lesson"
    assert after["books"]["book"]["pieces"]["two"]["completed_at"] == "2026-09-05T15:00:00+00:00"
    assert "three" not in after["books"]["book"]["pieces"]


def test_correct_current_piece_never_completes_previous():
    after = change(current(), "CORRECT", product_id="book", piece_id="three")
    assert after["books"]["book"]["pieces"] == {}


def test_correct_book_retains_previous_progress_and_does_not_claim_delivery():
    before = change(current(), "HISTORY", product_id="book", piece_id="two", statuses={"three": "COMPLETED"})
    after = change(before, "CORRECT", product_id="next", piece_id="four")
    assert after["books"]["book"] == before["books"]["book"]
    assert after["product_id"] == "next"
    assert "delivered_at" not in after["books"]["next"]


@pytest.mark.parametrize("action,kwargs", [
    ("COMPLETE_PIECE", {"piece_id": None}),
    ("COMPLETE_PIECE", {"piece_id": "four"}),
    ("COMPLETE_PIECE", {"piece_id": "two"}),
    ("COMPLETE_BOOK", {}),
    ("NEXT_BOOK", {"product_id": "next", "piece_id": "four"}),
    ("HISTORY", {"product_id": "book", "piece_id": "two", "statuses": {"four": "COMPLETED"}}),
    ("CORRECT", {"product_id": "book", "piece_id": "four"}),
])
def test_invalid_transitions_are_rejected(action, kwargs):
    with pytest.raises(HTTPException):
        change(current(), action, **kwargs)


def test_last_piece_then_explicit_book_transition():
    state = change(current(), "HISTORY", product_id="book", piece_id="two", statuses={"one": "COMPLETED", "three": "COMPLETED"})
    state = change(state, "COMPLETE_PIECE", piece_id=None)
    assert not state["books"]["book"]["completed"]
    state = change(state, "COMPLETE_BOOK")
    state = change(state, "NEXT_BOOK", product_id="next", piece_id="four")
    assert state["books"]["book"]["completed"]
    assert state["product_id"] == "next"


def test_baseline_does_not_erase_real_dates_when_status_unchanged():
    state = change(current(), "COMPLETE_PIECE", piece_id="one")
    after = change(state, "HISTORY", product_id="book", piece_id="one", statuses={"two": "COMPLETED"})
    assert after["books"]["book"]["pieces"]["two"] == state["books"]["book"]["pieces"]["two"]


def test_continue_does_not_complete_or_change_piece():
    assert change(current(), "CONTINUE") == current()


def test_stale_revision_cannot_overwrite_another_teachers_changes():
    db = MagicMock()
    with patch("app.api.routes.repertoire._require_learning_access"), patch("app.api.routes.repertoire.learning_snapshot", return_value={"revision": 3, "state": current()}):
        with pytest.raises(HTTPException) as exc:
            professor_change_learning(uuid4(), LearningChange(revision=2, session_id=uuid4(), action="CONTINUE"), db, SimpleNamespace(id=uuid4()))
    assert exc.value.status_code == 409
    db.commit.assert_not_called()


@pytest.mark.parametrize("own,latest,action", [(False, True, "CORRECT"), (True, False, "CORRECT"), (True, True, "UNDO")])
def test_undo_cannot_erase_someone_elses_or_later_change(own, latest, action):
    db = MagicMock()
    student, actor_id, event_id = uuid4(), uuid4(), uuid4()
    db.get.return_value = SimpleNamespace(student_id=student, actor_id=actor_id if own else uuid4(), revision=2 if latest else 1, action=action)
    with patch("app.api.routes.repertoire._require_learning_access"), patch("app.api.routes.repertoire.learning_snapshot", return_value={"revision": 2, "state": current()}):
        with pytest.raises(HTTPException):
            professor_change_learning(student, LearningChange(revision=2, session_id=uuid4(), action="UNDO", undo_event_id=event_id), db, SimpleNamespace(id=actor_id))
    db.commit.assert_not_called()


def test_access_requires_student_booking_in_requested_teacher_session():
    db = MagicMock()
    db.scalar.side_effect = [SimpleNamespace(id=uuid4()), None]
    with pytest.raises(HTTPException) as exc:
        _require_learning_access(db, SimpleNamespace(email="teacher@example.test"), uuid4(), uuid4())
    assert exc.value.status_code == 403
