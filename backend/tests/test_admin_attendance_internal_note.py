from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.api.routes.admin import update_admin_session_booking_attendance
from app.models.catalog import BookingStatus
from app.schemas.admin import AdminSessionBookingAttendanceUpdateRequest


class _FakeDb:
    def __init__(self, *scalar_results: object) -> None:
        self.scalar_results = list(scalar_results)
        self.commits = 0

    def scalar(self, _statement: object) -> object:
        return self.scalar_results.pop(0)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, _value: object) -> None:
        return None


def _run_update(payload: AdminSessionBookingAttendanceUpdateRequest, initial_note: str) -> SimpleNamespace:
    session_id = uuid4()
    booking_id = uuid4()
    user_id = uuid4()
    session = SimpleNamespace(id=session_id)
    booking = SimpleNamespace(
        id=booking_id,
        session_id=session_id,
        user_id=user_id,
        status=BookingStatus.ATTENDED,
        client_plan_subscription_id=None,
        cancelled_at=None,
        cancellation_reason=None,
        internal_note=initial_note,
    )
    client = SimpleNamespace(id=user_id)
    db = _FakeDb(session, booking, client)

    with patch("app.api.routes.admin._to_admin_session_booking_out", return_value=booking):
        result = update_admin_session_booking_attendance(
            session_id=session_id,
            booking_id=booking_id,
            payload=payload,
            db=db,
            actor=SimpleNamespace(id=uuid4()),
        )

    assert result is booking
    assert db.commits == 1
    return booking


def test_attendance_submit_saves_internal_note_when_field_is_present() -> None:
    booking = _run_update(
        AdminSessionBookingAttendanceUpdateRequest(
            attendance_status="ATTENDED",
            internal_note="Nouvelle note",
        ),
        initial_note="Ancienne note",
    )
    assert booking.internal_note == "Nouvelle note"


def test_attendance_submit_preserves_note_when_field_is_omitted() -> None:
    booking = _run_update(
        AdminSessionBookingAttendanceUpdateRequest(attendance_status="ATTENDED"),
        initial_note="Note existante",
    )
    assert booking.internal_note == "Note existante"
