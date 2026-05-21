from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.reports import _quote_family_child_schedule
from app.api.routes.reports import _merge_quote_family_groups_by_child_surname


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

    def test_child_schedule_falls_back_to_planning_blocks_by_order(self) -> None:
        quote = SimpleNamespace(
            estimated_solfege_level=None,
            selected_solfege_slot={},
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Cours de piano collectif en presentiel (1h)",
                        "weekday_label": "Mardi",
                        "start_time": "16:00",
                        "end_time": "17:00",
                        "location_label": "Rue de la Pompe",
                    },
                    {
                        "activity_label": "Cours de piano collectif en presentiel (1h)",
                        "weekday_label": "Jeudi",
                        "start_time": "18:00",
                        "end_time": "19:00",
                        "location_label": "Rue Scheffer",
                    },
                ]
            },
        )
        lines = [
            SimpleNamespace(
                title="Cours de piano collectif en presentiel (1h)",
                description=None,
                code=None,
                line_category="service",
                line_type="activity",
                master_item_type=None,
                activity_id="piano-main",
                meta={},
            ),
            SimpleNamespace(
                title="Cours de piano collectif en presentiel (1h)",
                description=None,
                code=None,
                line_category="service",
                line_type="activity",
                master_item_type=None,
                activity_id="piano-second",
                meta={},
            ),
        ]

        schedule = _quote_family_child_schedule(quote, lines)

        self.assertEqual(schedule["course_1"], "Mardi · 16:00-17:00 · Rue de la Pompe")
        self.assertEqual(schedule["course_2"], "Jeudi · 18:00-19:00 · Rue Scheffer")

    def test_merge_quote_family_groups_with_same_child_surname(self) -> None:
        now = datetime(2026, 5, 21, tzinfo=timezone.utc)
        grouped = {
            "email:a": {
                "family_key": "email:a",
                "family_label": "Suzanne Rossillon",
                "parent_email": "a@example.com",
                "quote_count": 2,
                "children": [{"child_name": "Alix Tardieu"}, {"child_name": "Azenor Tardieu"}],
            },
            "email:b": {
                "family_key": "email:b",
                "family_label": "Suzanne Rossillon",
                "parent_email": "b@example.com",
                "quote_count": 2,
                "children": [{"child_name": "Elisa Tardieu"}, {"child_name": "Virgile Tardieu"}],
            },
        }

        merged, _ = _merge_quote_family_groups_by_child_surname(grouped, {"email:a": now, "email:b": now})

        self.assertEqual(list(merged), ["child-surname:tardieu"])
        family = merged["child-surname:tardieu"]
        self.assertEqual(family["family_label"], "Famille Tardieu")
        self.assertEqual(len(family["children"]), 4)


if __name__ == "__main__":
    unittest.main()
