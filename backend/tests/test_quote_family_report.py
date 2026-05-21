from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.reports import _quote_family_child_schedule


class QuoteFamilyReportTests(unittest.TestCase):
    def test_child_schedule_uses_each_line_recommendation_key(self) -> None:
        quote = SimpleNamespace(
            estimated_solfege_level="3",
            selected_solfege_slot={},
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_id": "piano",
                        "activity_label": "Cours collectif",
                        "recommendation_key": "piano:main",
                        "weekday_label": "Lundi",
                        "start_time": "17:00",
                        "end_time": "18:00",
                        "location_label": "Rue de la Pompe",
                    },
                    {
                        "activity_id": "piano",
                        "activity_label": "Cours collectif",
                        "recommendation_key": "piano:second",
                        "weekday_label": "Mercredi",
                        "start_time": "16:00",
                        "end_time": "17:00",
                        "location_label": "Rue Scheffer",
                    },
                    {
                        "activity_id": "solfege",
                        "activity_label": "Solfege niveau 3",
                        "recommendation_key": "solfege:online_solfege",
                        "pending_solfege_level": "3",
                        "weekday_label": "Mercredi",
                        "start_time": "19:30",
                        "end_time": "20:15",
                        "location_label": "Online",
                    },
                ]
            },
        )
        lines = [
            SimpleNamespace(
                title="Cours de piano collectif",
                description=None,
                code=None,
                line_category="service",
                line_type="activity",
                master_item_type=None,
                activity_id="piano",
                meta={"typeform_automatic_line": "main"},
            ),
            SimpleNamespace(
                title="Cours de piano collectif 2e cours",
                description=None,
                code=None,
                line_category="service",
                line_type="activity",
                master_item_type=None,
                activity_id="piano",
                meta={"typeform_automatic_line": "second"},
            ),
            SimpleNamespace(
                title="Solfege niveau 3",
                description=None,
                code=None,
                line_category="service",
                line_type="activity",
                master_item_type=None,
                activity_id="solfege",
                meta={"typeform_automatic_line": "online_solfege"},
            ),
        ]

        schedule = _quote_family_child_schedule(quote, lines)

        self.assertEqual(schedule["course_1"], "Lundi · 17:00-18:00 · Rue de la Pompe")
        self.assertEqual(schedule["course_2"], "Mercredi · 16:00-17:00 · Rue Scheffer")
        self.assertEqual(schedule["solfege"], "Niveau 3 · Mercredi · 19:30-20:15 · Online")


if __name__ == "__main__":
    unittest.main()
