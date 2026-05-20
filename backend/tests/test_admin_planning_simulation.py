from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.admin import (
    _parse_school_year_bounds,
    _planning_simulation_clean_location_label,
    _planning_simulation_quote_person_key,
    _planning_simulation_quote_location_name,
    _planning_simulation_search_text,
    _planning_simulation_select_live_slot_for_quote,
    _safe_zoneinfo,
)
from app.models.catalog import DeliveryMode


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

    def test_safe_zoneinfo_falls_back_for_missing_or_invalid_timezone(self) -> None:
        self.assertEqual(_safe_zoneinfo(None).key, "Europe/Paris")
        self.assertEqual(_safe_zoneinfo("not-a-timezone").key, "Europe/Paris")
        self.assertEqual(_safe_zoneinfo("UTC").key, "UTC")

    def test_planning_simulation_hides_uuid_location_labels(self) -> None:
        self.assertEqual(
            _planning_simulation_clean_location_label("1be3c4dc-2f55-4712-bcf9-32a4624ff1ad"),
            "",
        )

    def test_planning_simulation_search_text_strips_accents(self) -> None:
        self.assertEqual(
            _planning_simulation_search_text("Cours collectif Éveil musical - Répétition"),
            "cours collectif eveil musical - repetition",
        )

    def test_planning_simulation_selects_least_loaded_live_slot_for_quote(self) -> None:
        slot_entries = {
            "series:full": {
                "capacity_max": 6,
                "_booked_user_ids": {"1", "2", "3", "4", "5", "6"},
                "_approved_quote_ids": set(),
                "_pending_quote_ids": set(),
                "_draft_quote_ids": set(),
            },
            "series:available": {
                "capacity_max": 6,
                "_booked_user_ids": {"1", "2"},
                "_approved_quote_ids": {"quote-1"},
                "_pending_quote_ids": set(),
                "_draft_quote_ids": set(),
            },
        }

        self.assertEqual(
            _planning_simulation_select_live_slot_for_quote(slot_entries, ["series:full", "series:available"]),
            "series:available",
        )

    def test_planning_simulation_labels_online_quote_slots(self) -> None:
        label = _planning_simulation_quote_location_name(
            {"activity_label": "Cours de solfege - Niveau 1"},
            course_type=SimpleNamespace(mode=DeliveryMode.ONLINE),
        )

        self.assertEqual(label, "En ligne")

    def test_planning_simulation_falls_back_to_unknown_location_label(self) -> None:
        self.assertEqual(_planning_simulation_quote_location_name({}), "Lieu non defini")

    def test_planning_simulation_quote_person_key_prefers_client(self) -> None:
        quote = SimpleNamespace(client_id="client-id", prospect_id="prospect-id")
        prospect = SimpleNamespace(linked_client_id="linked-client-id")

        self.assertEqual(_planning_simulation_quote_person_key(quote, prospect), "client:client-id")

    def test_planning_simulation_quote_person_key_uses_linked_prospect_client(self) -> None:
        quote = SimpleNamespace(client_id=None, prospect_id="prospect-id")
        prospect = SimpleNamespace(linked_client_id="linked-client-id")

        self.assertEqual(_planning_simulation_quote_person_key(quote, prospect), "client:linked-client-id")


if __name__ == "__main__":
    unittest.main()
