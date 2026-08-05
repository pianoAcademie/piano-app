from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.clients import (
    _eligible_formula_options_for_member,
    _is_piano_trial_formula_option,
)
from app.models.plan import PlanKind
from app.schemas.user import ClientSessionFormulaOptionOut


def _formula_option(*, code: str, name: str, description: str | None = None) -> ClientSessionFormulaOptionOut:
    return ClientSessionFormulaOptionOut(
        formula_id=uuid4(),
        formula_code=code,
        formula_type=PlanKind.PACK,
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
        )
        self.pack = _formula_option(
            code="PACK_10_PIANO_ONSITE",
            name="Carnet 10 cours piano en présentiel",
        )

    def test_detects_piano_trial_formula_from_code_and_name(self) -> None:
        self.assertTrue(_is_piano_trial_formula_option(self.trial))
        self.assertFalse(_is_piano_trial_formula_option(self.pack))

    @patch("app.api.routes.clients._member_has_prior_piano_booking", return_value=True)
    def test_excludes_trial_when_member_already_booked_piano(self, prior_booking: object) -> None:
        result = _eligible_formula_options_for_member(
            SimpleNamespace(),
            member_id=self.member_id,
            course_type=self.course_type,
            formula_options=[self.trial, self.pack],
        )

        self.assertEqual(result, [self.pack])
        prior_booking.assert_called_once()

    @patch("app.api.routes.clients._member_has_prior_piano_booking", return_value=False)
    def test_keeps_trial_for_first_piano_booking(self, prior_booking: object) -> None:
        result = _eligible_formula_options_for_member(
            SimpleNamespace(),
            member_id=self.member_id,
            course_type=self.course_type,
            formula_options=[self.trial, self.pack],
        )

        self.assertEqual(result, [self.trial, self.pack])
        prior_booking.assert_called_once()

    @patch("app.api.routes.clients._member_has_prior_piano_booking")
    def test_skips_history_query_without_trial_formula(self, prior_booking: object) -> None:
        result = _eligible_formula_options_for_member(
            SimpleNamespace(),
            member_id=self.member_id,
            course_type=self.course_type,
            formula_options=[self.pack],
        )

        self.assertEqual(result, [self.pack])
        prior_booking.assert_not_called()


if __name__ == "__main__":
    unittest.main()
