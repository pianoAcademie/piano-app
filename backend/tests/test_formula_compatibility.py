from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.bookings import _plan_supports_course_access, _select_eligible_subscription
from app.api.routes.clients import _active_formula_options_for_course_type, _family_plan_mini_out, _session_purchase_catalog
from app.models.plan import PlanKind, SubscriptionStatus


class _ScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = list(rows)

    def all(self) -> list[object]:
        return list(self._rows)


class _ExecuteResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = list(rows)

    def all(self) -> list[tuple[object, ...]]:
        return list(self._rows)


class _FakeSession:
    def __init__(
        self,
        *,
        scalar_values: list[object] | None = None,
        scalar_rows: list[object] | None = None,
        scalar_rows_sequence: list[list[object]] | None = None,
        execute_rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self._scalar_values = list(scalar_values or [])
        self._scalar_rows = list(scalar_rows or [])
        self._scalar_rows_sequence = [list(rows) for rows in (scalar_rows_sequence or [])]
        self._execute_rows = list(execute_rows or [])
        self.added: list[object] = []

    def scalar(self, _query: object) -> object | None:
        if self._scalar_values:
            return self._scalar_values.pop(0)
        return None

    def scalars(self, _query: object) -> _ScalarResult:
        if self._scalar_rows_sequence:
            return _ScalarResult(self._scalar_rows_sequence.pop(0))
        return _ScalarResult(self._scalar_rows)

    def execute(self, _query: object) -> _ExecuteResult:
        return _ExecuteResult(self._execute_rows)

    def add(self, obj: object) -> None:
        self.added.append(obj)


class FormulaCompatibilityTests(unittest.TestCase):
    def test_family_subscription_plan_includes_private_formula_price(self) -> None:
        plan = SimpleNamespace(
            id=uuid4(),
            code="FORM_TEST_PAYPLUG",
            name="Test Payplug 1 euro",
            kind=PlanKind.SUBSCRIPTION,
        )
        owner = SimpleNamespace(residence_country="FR", preferred_currency="EUR")
        now = datetime(2026, 7, 16, tzinfo=timezone.utc)

        with patch(
            "app.api.routes.clients._plan_amount_due_and_currency",
            return_value=(Decimal("1.00"), "EUR"),
        ):
            result = _family_plan_mini_out(
                _FakeSession(),
                plan=plan,
                owner=owner,
                on_date=now,
            )

        self.assertEqual(result.price_ttc, Decimal("1.00"))
        self.assertEqual(result.currency_code, "EUR")

    def test_pack_matches_course_access_via_credit_type(self) -> None:
        plan_id = uuid4()
        course_type_id = uuid4()
        credit_type_id = uuid4()
        fake_db = _FakeSession(scalar_values=[None, uuid4()])

        supported = _plan_supports_course_access(
            fake_db,
            plan_id=plan_id,
            plan_kind=PlanKind.PACK,
            course_type_id=course_type_id,
            credit_type_id=credit_type_id,
        )

        self.assertTrue(supported)

    def test_formula_options_include_pack_matched_by_credit_type(self) -> None:
        plan = SimpleNamespace(
            id=uuid4(),
            code="FORM-STUDIO-1",
            kind=PlanKind.PACK,
            name="1 reservation de studio",
            description="Pack studio",
            options_json=[],
            payment_methods_json=["CARD_ONLINE"],
            monthly_price_value=15,
            monthly_price_excl_vat=None,
            currency_code="EUR",
        )
        credit_type_id = uuid4()
        fake_db = _FakeSession(
            execute_rows=[(plan, None, None, None, credit_type_id)],
        )

        options = _active_formula_options_for_course_type(
            fake_db,
            course_type_id=uuid4(),
            course_type_name="Reservation studio de repetition",
            course_type_service_code="STUDIO_BOOKING",
            credit_type_id=credit_type_id,
            allowed_plan_kinds={PlanKind.PACK},
        )

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].formula_code, "FORM-STUDIO-1")
        self.assertEqual(options[0].restriction_labels, ["Reservation studio de repetition"])

    def test_select_eligible_subscription_accepts_pack_matched_by_credit_type(self) -> None:
        subscription = SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            plan_id=uuid4(),
            status=SubscriptionStatus.ACTIVE,
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ends_at=None,
            credits_remaining=3,
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            bookings_blocked=False,
            cancellation_effective_at=None,
            suspension_starts_at=None,
            suspension_ends_at=None,
        )
        plan = SimpleNamespace(
            id=subscription.plan_id,
            kind=PlanKind.PACK,
            active=True,
        )
        course_type = SimpleNamespace(
            id=uuid4(),
            credit_type_id=uuid4(),
            name="Reservation studio de repetition",
            service_code="STUDIO_BOOKING",
        )
        fake_db = _FakeSession(
            scalar_values=[course_type, None, uuid4()],
            execute_rows=[(subscription, plan)],
        )

        selected = _select_eligible_subscription(
            fake_db,
            user_id=subscription.user_id,
            course_type_id=course_type.id,
            now=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
            requested_subscription_id=None,
            allowed_plan_kinds={PlanKind.PACK},
        )

        self.assertIsNotNone(selected)
        selected_subscription, selected_plan = selected
        self.assertIs(selected_subscription, subscription)
        self.assertIs(selected_plan, plan)

    def test_pending_migrated_pack_is_eligible_only_in_read_only_preview(self) -> None:
        subscription = SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            plan_id=uuid4(),
            status=SubscriptionStatus.PENDING,
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ends_at=None,
            credits_remaining=3,
            created_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
            bookings_blocked=False,
            cancellation_effective_at=None,
            suspension_starts_at=None,
            suspension_ends_at=None,
        )
        plan = SimpleNamespace(id=subscription.plan_id, kind=PlanKind.PACK, active=True)
        course_type = SimpleNamespace(
            id=uuid4(),
            credit_type_id=uuid4(),
            name="Reservation studio de repetition",
            service_code="STUDIO_BOOKING",
        )
        fake_db = _FakeSession(
            scalar_values=[course_type, None, uuid4()],
            execute_rows=[(subscription, plan)],
        )

        selected = _select_eligible_subscription(
            fake_db,
            user_id=subscription.user_id,
            course_type_id=course_type.id,
            now=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
            requested_subscription_id=None,
            allowed_plan_kinds={PlanKind.PACK},
            include_pending_preview=True,
        )

        self.assertEqual(selected, (subscription, plan))

    def test_formula_options_include_entitlement_with_same_activity_name(self) -> None:
        plan = SimpleNamespace(
            id=uuid4(),
            code="FORM-STUDIO-10",
            kind=PlanKind.PACK,
            name="10 reservations de studio",
            description="Pack studio 10",
            options_json=[],
            payment_methods_json=["CARD_ONLINE"],
            monthly_price_value=130,
            monthly_price_excl_vat=None,
            currency_code="EUR",
        )
        fake_db = _FakeSession(
            execute_rows=[(plan, uuid4(), "Réservation studio de répétition", "STUDIO_BOOKING", None)],
        )

        options = _active_formula_options_for_course_type(
            fake_db,
            course_type_id=uuid4(),
            course_type_name="Reservation studio de repetition",
            course_type_service_code="STUDIO_BOOKING",
            credit_type_id=None,
            allowed_plan_kinds={PlanKind.PACK},
        )

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].formula_code, "FORM-STUDIO-10")

    def test_formula_options_include_exact_entitlement_match(self) -> None:
        plan = SimpleNamespace(
            id=uuid4(),
            code="FORM-STUDIO-EXACT",
            kind=PlanKind.PACK,
            name="Reservation studio",
            description="Pack studio exact",
            options_json=[],
            payment_methods_json=["CARD_ONLINE"],
            monthly_price_value=15,
            monthly_price_excl_vat=None,
            currency_code="EUR",
        )
        course_type_id = uuid4()
        fake_db = _FakeSession(
            execute_rows=[(plan, course_type_id, "Reservation studio de repetition", None, None)],
        )

        options = _active_formula_options_for_course_type(
            fake_db,
            course_type_id=course_type_id,
            course_type_name="Réservation studio de répétition",
            course_type_service_code="STUDIO_BOOKING",
            credit_type_id=None,
            allowed_plan_kinds={PlanKind.PACK},
        )

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].formula_code, "FORM-STUDIO-EXACT")

    def test_session_purchase_catalog_uses_account_currency_when_session_has_no_currency_field(self) -> None:
        plan = SimpleNamespace(
            id=uuid4(),
            code="FORM-STUDIO-1",
            kind=PlanKind.PACK,
            name="1 reservation de studio",
            description="Pack studio",
            options_json=[],
            payment_methods_json=["CARD_ONLINE"],
            monthly_price_value=15,
            monthly_price_excl_vat=None,
            currency_code="EUR",
        )
        credit_type_id = uuid4()
        fake_db = _FakeSession(
            scalar_values=["EUR"],
            execute_rows=[(plan, uuid4(), "Reservation studio de repetition", "STUDIO", credit_type_id)],
        )
        session_obj = SimpleNamespace(
            visibility_scope="EXTERNAL",
            booking_scope="EXTERNAL",
            is_private=False,
            allow_online_booking=True,
            external_booking_price_ttc=15,
            start_at_utc=datetime(2026, 7, 16, 10, 0, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 7, 16, 11, 0, tzinfo=timezone.utc),
        )
        course_type = SimpleNamespace(
            id=uuid4(),
            name="Reservation studio de repetition",
            service_code="STUDIO",
            credit_type_id=credit_type_id,
            allows_student_bookings=True,
        )

        formula_options, direct_payment_amount, direct_payment_currency, session_booking_scopes = _session_purchase_catalog(
            fake_db,
            session_obj=session_obj,
            course_type=course_type,
        )

        self.assertEqual(len(formula_options), 1)
        self.assertEqual(formula_options[0].formula_code, "FORM-STUDIO-1")
        self.assertEqual(str(direct_payment_amount), "15.00")
        self.assertEqual(direct_payment_currency, "EUR")
        self.assertEqual([scope.value for scope in session_booking_scopes], ["EXTERNAL"])


if __name__ == "__main__":
    unittest.main()
