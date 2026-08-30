from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.api.routes.admin_to_process import _statement_session_candidates
from app.services.teacher_invoicing import ComputedStatement, ComputedStatementLine


def _statement(*, course_type_id=None, service_date: str = "2026-08-06", location: str = "Rue de Richelieu"):
    course_type_id = course_type_id or uuid4()
    session_id = uuid4()
    line = ComputedStatementLine(
        course_type_id=course_type_id,
        course_type_label="Cours collectifs ado/adultes",
        hours=Decimal("1.00"),
        unit_rate_ht=Decimal("32.00"),
        amount_ht=Decimal("32.00"),
        amount_ttc=Decimal("32.00"),
        meta={
            "session_items": [
                {
                    "session_id": str(session_id),
                    "title": "Cours collectif adultes",
                    "date": service_date,
                    "location_name": location,
                    "unit_rate_ht": "32.00",
                }
            ]
        },
    )
    statement = ComputedStatement(
        teacher_id=uuid4(),
        payor_legal_entity_id=uuid4(),
        payor_legal_entity_name="PIANO ACADEMIE",
        year=2026,
        month=8,
        attendance_complete=True,
        currency="EUR",
        totals_ht=Decimal("96.00"),
        totals_vat=Decimal("0.00"),
        totals_ttc=Decimal("96.00"),
        lines=[line],
        missing_sessions=[],
    )
    return statement, course_type_id, session_id


class MissingServiceCandidateTests(unittest.TestCase):
    def test_matches_date_location_and_course_type(self) -> None:
        statement, course_type_id, session_id = _statement()

        candidates = _statement_session_candidates(
            [statement],
            service_date=date(2026, 8, 6),
            location_name="rue de richelieu",
            course_type_id=str(course_type_id),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][1]["session_id"], str(session_id))

    def test_rejects_wrong_location(self) -> None:
        statement, course_type_id, _ = _statement()

        candidates = _statement_session_candidates(
            [statement],
            service_date=date(2026, 8, 6),
            location_name="Rue d'Assas",
            course_type_id=str(course_type_id),
        )

        self.assertEqual(candidates, [])

    def test_falls_back_to_date_and_location_after_admin_corrects_course_type(self) -> None:
        statement, _, session_id = _statement()

        candidates = _statement_session_candidates(
            [statement],
            service_date=date(2026, 8, 6),
            location_name="Rue de Richelieu",
            course_type_id=str(uuid4()),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][1]["session_id"], str(session_id))


if __name__ == "__main__":
    unittest.main()
