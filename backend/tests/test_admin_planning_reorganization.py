from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch
from uuid import uuid4

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin import (
    _move_planning_reorganization_booking_occurrence,
    _planning_reorganization_move_pairs,
    _planning_reorganization_price_rows,
    move_planning_reorganization_booking,
)
from app.models.catalog import BookingReorganizationLink
from app.models.catalog import BookingStatus, SessionStatus
from app.schemas.admin import AdminPlanningReorganizationMoveRequest


class _FakeSession:
    def __init__(self, scalar_values: list[object], scalars_values: list[list[object]] | None = None) -> None:
        self._scalar_values = list(scalar_values)
        self._scalars_values = list(scalars_values or [])
        self.commit_count = 0
        self.added_rows: list[object] = []

    def scalar(self, _query: object) -> object | None:
        return self._scalar_values.pop(0) if self._scalar_values else None

    def scalars(self, _query: object) -> SimpleNamespace:
        values = self._scalars_values.pop(0) if self._scalars_values else []
        return SimpleNamespace(all=lambda: values)

    def commit(self) -> None:
        self.commit_count += 1

    def add(self, row: object) -> None:
        self.added_rows.append(row)


class AdminPlanningReorganizationTests(unittest.TestCase):
    def test_series_move_matches_different_weekdays_in_the_same_week(self) -> None:
        wednesday = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)
        saturday = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
        booking = SimpleNamespace(
            id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            status=BookingStatus.BOOKED,
            booked_at=wednesday - timedelta(days=30),
        )
        source_session = SimpleNamespace(
            id=booking.session_id,
            recurrence_group_id=uuid4(),
            start_at_utc=wednesday,
            timezone="Europe/Paris",
        )
        target_session = SimpleNamespace(
            id=uuid4(),
            recurrence_group_id=uuid4(),
            start_at_utc=saturday,
            timezone="Europe/Paris",
        )
        db = _FakeSession([], scalars_values=[[booking]])

        with patch(
            "app.api.routes.admin._target_sessions_for_scope",
            side_effect=[[source_session], [target_session]],
        ):
            pairs, skipped, details = _planning_reorganization_move_pairs(
                db,  # type: ignore[arg-type]
                source_booking=booking,
                source_session=source_session,
                target_session=target_session,
                scope="series_future",
            )

        assert pairs == [(booking, source_session, target_session)]
        assert skipped == 0
        assert details == []

    def test_reused_cancelled_target_keeps_a_neutral_financial_link(self) -> None:
        now = datetime.now(timezone.utc)
        user_id = uuid4()
        subscription_id = uuid4()
        source = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            status=BookingStatus.BOOKED,
            client_plan_subscription_id=subscription_id,
            booked_at=now - timedelta(days=10),
            cancelled_at=None,
            cancellation_reason=None,
            price_excl_vat_snapshot=Decimal("30.00"),
            vat_rate_snapshot=Decimal("20.00"),
            vat_amount_snapshot=Decimal("6.00"),
            total_incl_vat_snapshot=Decimal("36.00"),
            currency_snapshot="EUR",
            pricing_snapshot_locked=True,
            student_note=None,
            internal_note=None,
            student_start_at_utc=None,
            student_end_at_utc=None,
            is_trial_course=False,
        )
        target = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            status=BookingStatus.CANCELLED,
        )
        source_session = SimpleNamespace(id=uuid4())
        target_session = SimpleNamespace(
            id=uuid4(),
            status=SessionStatus.SCHEDULED,
            course_type_id=uuid4(),
            location_id=uuid4(),
            start_at_utc=now + timedelta(days=30),
        )
        course_type = SimpleNamespace(allows_student_bookings=True)
        participant = SimpleNamespace(id=user_id, client_kind="CHILD")
        db = _FakeSession([course_type, participant, target, None])

        with patch("app.api.routes.admin._session_client_kind_allowed", return_value=True), patch(
            "app.api.routes.admin._participant_capacity_block_reason",
            return_value=None,
        ), patch("app.api.routes.admin.skip_pending_reminders_for_booking"), patch(
            "app.api.routes.admin.cancel_pending_booking_reminder_notifications"
        ), patch("app.api.routes.admin.ensure_booking_reminder"):
            moved, detail = _move_planning_reorganization_booking_occurrence(
                db,  # type: ignore[arg-type]
                booking=source,
                source_session=source_session,
                target_session=target_session,
                now=now,
                lock_price_snapshot=True,
            )

        assert moved is True
        assert detail is None
        assert source.status == BookingStatus.CANCELLED
        assert target.status == BookingStatus.BOOKED
        links = [row for row in db.added_rows if isinstance(row, BookingReorganizationLink)]
        assert len(links) == 1
        assert links[0].source_booking_id == source.id
        assert links[0].target_booking_id == target.id
        assert links[0].financially_neutral is True

    def test_same_forfait_move_is_not_treated_as_a_price_change(self) -> None:
        subscription_id = uuid4()
        booking = SimpleNamespace(
            id=uuid4(),
            client_plan_subscription_id=subscription_id,
            price_excl_vat_snapshot=Decimal("30.00"),
            vat_rate_snapshot=Decimal("20.00"),
            vat_amount_snapshot=Decimal("6.00"),
            total_incl_vat_snapshot=Decimal("36.00"),
            currency_snapshot="EUR",
        )
        target_session = SimpleNamespace(id=uuid4())
        db = _FakeSession([], scalars_values=[[subscription_id]])

        with patch(
            "app.api.routes.admin._planning_reorganization_target_price_snapshot",
            return_value=(
                Decimal("31.67"),
                Decimal("20.00"),
                Decimal("6.33"),
                Decimal("38.00"),
                "EUR",
            ),
        ):
            rows = _planning_reorganization_price_rows(
                db,  # type: ignore[arg-type]
                pairs=[(booking, SimpleNamespace(), target_session)],
                now=datetime.now(timezone.utc),
            )

        assert rows == [
            (
                booking,
                (
                    Decimal("30.00"),
                    Decimal("20.00"),
                    Decimal("6.00"),
                    Decimal("36.00"),
                    "EUR",
                ),
                False,
            )
        ]

    def test_single_move_does_not_promote_waitlist_or_enqueue_notifications(self) -> None:
        now = datetime.now(timezone.utc)
        source_session_id = uuid4()
        source_booking = SimpleNamespace(
            id=uuid4(),
            session_id=source_session_id,
            status=BookingStatus.BOOKED,
        )
        source_session = SimpleNamespace(
            id=source_session_id,
            recurrence_group_id=uuid4(),
            status=SessionStatus.SCHEDULED,
            start_at_utc=now + timedelta(days=30),
        )
        target_session = SimpleNamespace(
            id=uuid4(),
            recurrence_group_id=uuid4(),
        )
        db = _FakeSession([source_booking, source_session, target_session])
        payload = AdminPlanningReorganizationMoveRequest(
            booking_id=source_booking.id,
            target_session_id=target_session.id,
            scope="single",
        )

        with patch(
            "app.api.routes.admin._planning_reorganization_price_rows",
            return_value=[(source_booking, (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "EUR"), False)],
        ), patch(
            "app.api.routes.admin._move_planning_reorganization_booking_occurrence",
            return_value=(True, None),
        ) as move_occurrence, patch(
            "app.api.routes.admin._promote_waitlist_if_possible",
        ) as promote_waitlist, patch(
            "app.api.routes.admin.enqueue_notifications",
        ) as enqueue_notifications:
            result = move_planning_reorganization_booking(
                payload,
                db=db,  # type: ignore[arg-type]
                _=SimpleNamespace(),  # type: ignore[arg-type]
            )

        self.assertEqual(result.moved_count, 1)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(db.commit_count, 1)
        move_occurrence.assert_called_once()
        promote_waitlist.assert_not_called()
        enqueue_notifications.assert_not_called()

    def test_future_series_move_does_not_promote_waitlist_or_enqueue_notifications(self) -> None:
        start_at = datetime.now(timezone.utc) + timedelta(days=30)
        source_session_id = uuid4()
        source_booking = SimpleNamespace(
            id=uuid4(),
            session_id=source_session_id,
            status=BookingStatus.BOOKED,
            user_id=uuid4(),
            booked_at=start_at - timedelta(days=30),
        )
        source_session = SimpleNamespace(
            id=source_session_id,
            recurrence_group_id=uuid4(),
            status=SessionStatus.SCHEDULED,
            start_at_utc=start_at,
            timezone="Europe/Paris",
        )
        target_session = SimpleNamespace(
            id=uuid4(),
            recurrence_group_id=uuid4(),
            start_at_utc=start_at,
            timezone="Europe/Paris",
        )
        db = _FakeSession(
            [source_booking, source_session, target_session],
            scalars_values=[[source_booking]],
        )
        payload = AdminPlanningReorganizationMoveRequest(
            booking_id=source_booking.id,
            target_session_id=target_session.id,
            scope="series_future",
        )

        with patch(
            "app.api.routes.admin._target_sessions_for_scope",
            side_effect=[[source_session], [target_session]],
        ) as target_sessions_for_scope, patch(
            "app.api.routes.admin._planning_reorganization_price_rows",
            return_value=[(source_booking, (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "EUR"), False)],
        ), patch(
            "app.api.routes.admin._move_planning_reorganization_booking_occurrence",
            return_value=(True, None),
        ) as move_occurrence, patch(
            "app.api.routes.admin._promote_waitlist_if_possible",
        ) as promote_waitlist, patch(
            "app.api.routes.admin.enqueue_notifications",
        ) as enqueue_notifications:
            result = move_planning_reorganization_booking(
                payload,
                db=db,  # type: ignore[arg-type]
                _=SimpleNamespace(),  # type: ignore[arg-type]
            )

        self.assertEqual(result.moved_count, 1)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(db.commit_count, 1)
        move_occurrence.assert_called_once()
        target_sessions_for_scope.assert_any_call(
            db,
            session_obj=source_session,
            apply_scope="SERIES_FUTURE",
        )
        target_sessions_for_scope.assert_any_call(
            db,
            session_obj=target_session,
            apply_scope="SERIES_FUTURE",
        )
        promote_waitlist.assert_not_called()
        enqueue_notifications.assert_not_called()

    def test_price_change_requires_an_explicit_choice(self) -> None:
        source_booking = SimpleNamespace(id=uuid4(), session_id=uuid4())
        source_session = SimpleNamespace(id=source_booking.session_id, recurrence_group_id=None)
        target_session = SimpleNamespace(id=uuid4(), recurrence_group_id=None)
        db = _FakeSession([source_booking, source_session, target_session])
        target_snapshot = (Decimal("100"), Decimal("20"), Decimal("20"), Decimal("120"), "EUR")
        payload = AdminPlanningReorganizationMoveRequest(
            booking_id=source_booking.id,
            target_session_id=target_session.id,
            scope="single",
        )

        with patch(
            "app.api.routes.admin._planning_reorganization_price_rows",
            return_value=[(source_booking, target_snapshot, True)],
        ), patch(
            "app.api.routes.admin._move_planning_reorganization_booking_occurrence",
        ) as move_occurrence:
            with self.assertRaises(HTTPException) as raised:
                move_planning_reorganization_booking(
                    payload,
                    db=db,  # type: ignore[arg-type]
                    _=SimpleNamespace(),  # type: ignore[arg-type]
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(db.commit_count, 0)
        move_occurrence.assert_not_called()

    def test_apply_target_price_passes_the_new_snapshot_to_the_move(self) -> None:
        source_booking = SimpleNamespace(id=uuid4(), session_id=uuid4())
        source_session = SimpleNamespace(id=source_booking.session_id, recurrence_group_id=None)
        target_session = SimpleNamespace(id=uuid4(), recurrence_group_id=None)
        db = _FakeSession([source_booking, source_session, target_session])
        target_snapshot = (Decimal("100"), Decimal("20"), Decimal("20"), Decimal("120"), "EUR")
        payload = AdminPlanningReorganizationMoveRequest(
            booking_id=source_booking.id,
            target_session_id=target_session.id,
            scope="single",
            price_policy="apply_target",
        )

        with patch(
            "app.api.routes.admin._planning_reorganization_price_rows",
            return_value=[(source_booking, target_snapshot, True)],
        ), patch(
            "app.api.routes.admin._move_planning_reorganization_booking_occurrence",
            return_value=(True, None),
        ) as move_occurrence:
            result = move_planning_reorganization_booking(
                payload,
                db=db,  # type: ignore[arg-type]
                _=SimpleNamespace(),  # type: ignore[arg-type]
            )

        self.assertEqual(result.moved_count, 1)
        self.assertEqual(db.commit_count, 1)
        move_occurrence.assert_called_once_with(
            db,
            booking=source_booking,
            source_session=source_session,
            target_session=target_session,
            now=ANY,
            target_price_snapshot=target_snapshot,
            lock_price_snapshot=True,
        )

    def test_keep_source_price_locks_the_existing_snapshot(self) -> None:
        source_booking = SimpleNamespace(id=uuid4(), session_id=uuid4())
        source_session = SimpleNamespace(id=source_booking.session_id, recurrence_group_id=None)
        target_session = SimpleNamespace(id=uuid4(), recurrence_group_id=None)
        db = _FakeSession([source_booking, source_session, target_session])
        target_snapshot = (Decimal("26.67"), Decimal("20"), Decimal("5.33"), Decimal("32"), "EUR")
        payload = AdminPlanningReorganizationMoveRequest(
            booking_id=source_booking.id,
            target_session_id=target_session.id,
            scope="single",
            price_policy="keep_source",
        )

        with patch(
            "app.api.routes.admin._planning_reorganization_price_rows",
            return_value=[(source_booking, target_snapshot, True)],
        ), patch(
            "app.api.routes.admin._move_planning_reorganization_booking_occurrence",
            return_value=(True, None),
        ) as move_occurrence:
            result = move_planning_reorganization_booking(
                payload,
                db=db,  # type: ignore[arg-type]
                _=SimpleNamespace(),  # type: ignore[arg-type]
            )

        self.assertEqual(result.moved_count, 1)
        self.assertEqual(db.commit_count, 1)
        move_occurrence.assert_called_once_with(
            db,
            booking=source_booking,
            source_session=source_session,
            target_session=target_session,
            now=ANY,
            target_price_snapshot=None,
            lock_price_snapshot=True,
        )


if __name__ == "__main__":
    unittest.main()
