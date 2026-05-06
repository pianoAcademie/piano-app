from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin import _parse_school_year_bounds


class AdminPlanningSimulationTests(unittest.TestCase):
    def test_parse_school_year_bounds_accepts_standard_label(self) -> None:
        self.assertEqual(
            _parse_school_year_bounds("2026-2027"),
            (date(2026, 9, 1), date(2027, 8, 31)),
        )

    def test_parse_school_year_bounds_rejects_invalid_label(self) -> None:
        self.assertIsNone(_parse_school_year_bounds(""))
        self.assertIsNone(_parse_school_year_bounds("2027-2026"))
        self.assertIsNone(_parse_school_year_bounds("saison"))


if __name__ == "__main__":
    unittest.main()
