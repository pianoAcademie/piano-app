from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.clients import (
    _active_formula_options_for_course_type,
    _eligible_formula_options_for_member,
    _is_piano_trial_formula_option,
    get_public_session_trial_offers,
)
from app.models.catalog import DeliveryMode, SessionAudienceScope
from app.models.plan import Plan, PlanKind
from app.schemas.user import ClientSessionFormulaOptionOut


def _formula_option(
    *,
    code: str,
    name: str,
    description: str | None = None,
    is_trial_offer: bool = False,
) -> ClientSessionFormulaOptionOut:
    return ClientSessionFormulaOptionOut(
        formula_id=uuid4(),
        formula_code=code,
        formula_type=PlanKind.PACK,
        is_trial_offer=is_trial_offer,
        name=name,
        description=description,
        currency="EUR",
    )


class ClientTrialFormulaEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.member_id = uuid4()
        self.course_type = SimpleNamespace(id=uuid4(), credit_type_id=uuid4())
        self.trial = _formula_option(
            code="PIANO_TRIAL_ONSITE",
            name="Cours d'essai de piano en présentiel",
            is_trial_offer=True,
        )
        self.pack = _formula_option(
            code="PACK_10_PIANO_ONSITE",
            name="Carnet 10 cours piano en présentiel",
        )

    def test_detects_only_explicit_trial_formula(self) -> None:
        self.assertTrue(_is_piano_trial_formula_option(self.trial))
        self.assertFalse(_is_piano_trial_formula_option(self.pack))

    @patch("app.api.routes.clients.has_prior_course_attendance_for_course_type", return_value=False)
    @patch("app.api.routes.clients.has_available_trial_credit_for_course_type", return_value=False)
    @patch("app.api.routes.clients.has_trial_booking_for_course_type", return_value=True)
    def test_excludes_trial_when_member_already_used_trial(
        self,
        prior_trial: object,
        available_credit: object,
        prior_attendance: object,
    ) -> None:
        result = _eligible_formula_options_for_member(
            SimpleNamespace(),
            member_id=self.member_id,
            course_type=self.course_type,
            formula_options=[self.trial, self.pack],
        )

        self.assertEqual(result, [self.pack])
        prior_trial.assert_called_once()
        available_credit.assert_called_once()
        prior_attendance.assert_called_once()

    @patch("app.api.routes.clients.resolve_session_visibility_scopes", return_value=[])
    @patch("app.api.routes.clients.scopes_allow_external_visibility", return_value=True)
    @patch("app.api.routes.clients._session_purchase_catalog")
    def test_public_session_catalog_exposes_only_trial_price(
        self,
        purchase_catalog: object,
        _external_visibility: object,
        _visibility_scopes: object,
    ) -> None:
        purchase_catalog.return_value = (
            [self.pack, self.trial],
            None,
            None,
            [SessionAudienceScope.EXTERNAL],
        )
        session = SimpleNamespace(id=uuid4())
        course_type = SimpleNamespace(allows_student_bookings=True)
        db = SimpleNamespace(
            execute=lambda _query: SimpleNamespace(first=lambda: (session, course_type))
        )

        result = get_public_session_trial_offers(session.id, db)

        self.assertEqual(result, [self.trial])

    @patch("app.api.routes.clients.has_prior_course_attendance_for_course_type", return_value=False)
    @patch("app.api.routes.clients.has_available_trial_credit_for_course_type", return_value=False)
    @patch("app.api.routes.clients.has_trial_booking_for_course_type", return_value=False)
    def test_keeps_trial_for_first_trial_booking(
        self,
        prior_trial: object,
        available_credit: object,
        prior_attendance: object,
    ) -> None:
        result = _eligible_formula_options_for_member(
            SimpleNamespace(),
            member_id=self.member_id,
            course_type=self.course_type,
            formula_options=[self.trial, self.pack],
        )

        self.assertEqual(result, [self.trial, self.pack])
        prior_trial.assert_called_once()
        available_credit.assert_called_once()
        prior_attendance.assert_called_once()

    @patch("app.api.routes.clients.has_prior_course_attendance_for_course_type")
    @patch("app.api.routes.clients.has_available_trial_credit_for_course_type")
    @patch("app.api.routes.clients.has_trial_booking_for_course_type")
    def test_skips_history_query_without_trial_formula(
        self,
        prior_trial: object,
        available_credit: object,
        prior_attendance: object,
    ) -> None:
        result = _eligible_formula_options_for_member(
            SimpleNamespace(),
            member_id=self.member_id,
            course_type=self.course_type,
            formula_options=[self.pack],
        )

        self.assertEqual(result, [self.pack])
        prior_trial.assert_not_called()
        available_credit.assert_not_called()
        prior_attendance.assert_not_called()

    @patch("app.api.routes.clients.has_prior_course_attendance_for_course_type", return_value=False)
    @patch("app.api.routes.clients.has_available_trial_credit_for_course_type", return_value=True)
    @patch("app.api.routes.clients.has_trial_booking_for_course_type", return_value=False)
    def test_excludes_second_purchase_when_trial_credit_is_already_available(
        self,
        _prior_trial: object,
        _available_credit: object,
        _prior_attendance: object,
    ) -> None:
        result = _eligible_formula_options_for_member(
            SimpleNamespace(),
            member_id=self.member_id,
            course_type=self.course_type,
            formula_options=[self.trial, self.pack],
        )

        self.assertEqual(result, [self.pack])

    @patch("app.api.routes.clients.has_prior_course_attendance_for_course_type", return_value=True)
    @patch("app.api.routes.clients.has_available_trial_credit_for_course_type", return_value=False)
    @patch("app.api.routes.clients.has_trial_booking_for_course_type", return_value=False)
    def test_excludes_trial_when_member_already_followed_course_type(
        self,
        _prior_trial: object,
        _available_credit: object,
        prior_attendance: object,
    ) -> None:
        result = _eligible_formula_options_for_member(
            SimpleNamespace(),
            member_id=self.member_id,
            course_type=self.course_type,
            formula_options=[self.trial, self.pack],
        )

        self.assertEqual(result, [self.pack])
        prior_attendance.assert_called_once()


class _RowsResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class _FormulaCatalogDb:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def execute(self, _query: object) -> _RowsResult:
        return _RowsResult(self._rows)


class ClientFormulaDeliveryModeTests(unittest.TestCase):
    def test_online_only_formula_is_not_offered_for_onsite_course(self) -> None:
        target_course_type_id = uuid4()
        online_course_type_id = uuid4()
        online_plan = Plan(
            id=uuid4(),
            code="MONTHLY_PIANO_ONLINE",
            name="Abonnement mensuel online + solfège - adultes",
            kind=PlanKind.SUBSCRIPTION,
            active=True,
            is_private=False,
            currency_code="EUR",
        )
        db = _FormulaCatalogDb(
            [
                (
                    online_plan,
                    online_course_type_id,
                    "Cours collectif",
                    "PIANO_CLASS",
                    DeliveryMode.ONLINE,
                    None,
                )
            ]
        )

        result = _active_formula_options_for_course_type(
            db,
            course_type_id=target_course_type_id,
            course_type_name="Cours collectif",
            course_type_service_code="PIANO_CLASS",
            course_type_mode=DeliveryMode.ONSITE,
            credit_type_id=uuid4(),
            allowed_plan_kinds={PlanKind.SUBSCRIPTION},
        )

        self.assertEqual(result, [])

    def test_multichannel_formula_with_exact_onsite_entitlement_remains_available(self) -> None:
        target_course_type_id = uuid4()
        multichannel_plan = Plan(
            id=uuid4(),
            code="PACK_10_PIANO_MULTI",
            name="Carnet 10 cours - multi canal",
            kind=PlanKind.PACK,
            active=True,
            is_private=False,
            currency_code="EUR",
        )
        db = _FormulaCatalogDb(
            [
                (
                    multichannel_plan,
                    target_course_type_id,
                    "Cours collectif",
                    "PIANO_CLASS",
                    DeliveryMode.ONSITE,
                    None,
                )
            ]
        )

        result = _active_formula_options_for_course_type(
            db,
            course_type_id=target_course_type_id,
            course_type_name="Cours collectif",
            course_type_service_code="PIANO_CLASS",
            course_type_mode=DeliveryMode.ONSITE,
            credit_type_id=uuid4(),
            allowed_plan_kinds={PlanKind.PACK},
        )

        self.assertEqual([option.formula_code for option in result], ["PACK_10_PIANO_MULTI"])


if __name__ == "__main__":
    unittest.main()
