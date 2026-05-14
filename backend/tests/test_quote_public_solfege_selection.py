from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import _public_quote_solfege_selection
from app.api.routes.quotes import _apply_selected_solfege_slot_to_calendar_snapshot
from app.api.routes.quotes import _calendar_snapshot_with_selected_solfege_block
from app.api.routes.quotes import _session_matches_quote_selected_solfege_slot
from app.models.catalog import DeliveryMode


class QuotePublicSolfegeSelectionTests(unittest.TestCase):
    def test_selected_solfege_slot_match_rejects_stale_manual_session(self) -> None:
        selected_slot = {
            "weekday": 4,
            "start_time": "18:35",
            "end_time": "19:20",
            "location_label": "En ligne",
            "modality": "online",
        }
        location = SimpleNamespace(name="Online", timezone="Europe/Paris")
        course_type = SimpleNamespace(mode=DeliveryMode.ONLINE)
        friday_session = SimpleNamespace(
            timezone="Europe/Paris",
            location_id=uuid4(),
            start_at_utc=datetime(2026, 10, 2, 16, 35, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 10, 2, 17, 20, tzinfo=timezone.utc),
        )
        wednesday_session = SimpleNamespace(
            timezone="Europe/Paris",
            location_id=uuid4(),
            start_at_utc=datetime(2026, 9, 30, 16, 35, tzinfo=timezone.utc),
            end_at_utc=datetime(2026, 9, 30, 17, 20, tzinfo=timezone.utc),
        )

        self.assertTrue(
            _session_matches_quote_selected_solfege_slot(
                friday_session,
                course_type=course_type,
                location=location,
                selected_slot=selected_slot,
                expected_date_set=set(),
            )
        )
        self.assertFalse(
            _session_matches_quote_selected_solfege_slot(
                wednesday_session,
                course_type=course_type,
                location=location,
                selected_slot=selected_slot,
                expected_date_set=set(),
            )
        )

    def test_selected_solfege_slot_adds_missing_planning_block(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            school_year_label="2026-2027",
            estimated_solfege_level="1",
            selected_solfege_slot={
                "weekday": 1,
                "weekday_label": "Mardi",
                "start_time": "17:05",
                "end_time": "17:50",
                "duration_minutes": 45,
                "location_label": "En ligne",
                "modality": "online",
                "label": "Mardi 17:05-17:50 · En ligne",
            },
            calendar_snapshot={"blocks": []},
        )
        line = SimpleNamespace(
            activity_id="activity-solfege-id",
            title="Cours de solfège - Niveau 1",
            description=None,
            code=None,
            duration_minutes=45,
            meta={"typeform_automatic_line": "online_solfege"},
        )

        snapshot = _calendar_snapshot_with_selected_solfege_block(quote, lines=[line])

        self.assertEqual(len(snapshot["blocks"]), 1)
        block = snapshot["blocks"][0]
        assert isinstance(block, dict)
        self.assertEqual(block["activity_id"], "activity-solfege-id")
        self.assertEqual(block["activity_label"], "Cours de solfège - Niveau 1")
        self.assertEqual(block["location_label"], "En ligne")
        self.assertEqual(block["start_time"], "17:05")
        self.assertEqual(block["recommendation_key"], "activity-solfege-id:online_solfege")
        self.assertTrue(block["selection_pending"])
        self.assertNotIn("start_date", block)
        self.assertNotIn("end_date", block)

    def test_selected_solfege_slot_refreshes_stale_planning_block(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            school_year_label="2026-2027",
            estimated_solfege_level="3",
            selected_solfege_slot={
                "weekday": 2,
                "weekday_label": "Mercredi",
                "start_time": "19:30",
                "end_time": "20:15",
                "duration_minutes": 45,
                "location_label": "En ligne",
                "modality": "online",
            },
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_id": "activity-solfege-id",
                        "activity_label": "Solfège niveau 3",
                        "weekday": 2,
                        "start_time": "19:30",
                        "end_time": "20:15",
                        "start_date": "2026-09-01",
                        "end_date": "2027-08-31",
                        "selection_pending": False,
                    }
                ],
                "sessions": [
                    {"activity_id": "activity-piano-id", "date": "2026-09-07"},
                    {"activity_id": "activity-solfege-id", "date": "2026-09-02"},
                ],
                "sessions_count": 2,
            },
        )
        line = SimpleNamespace(
            activity_id="activity-solfege-id",
            title="Solfège niveau 3",
            description=None,
            code=None,
            duration_minutes=45,
            meta={"typeform_automatic_line": "online_solfege"},
        )

        snapshot = _calendar_snapshot_with_selected_solfege_block(quote, lines=[line])

        self.assertEqual(len(snapshot["blocks"]), 1)
        block = snapshot["blocks"][0]
        assert isinstance(block, dict)
        self.assertTrue(block["selection_pending"])
        self.assertNotIn("start_date", block)
        self.assertNotIn("end_date", block)
        self.assertEqual(block["recommendation_key"], "activity-solfege-id:online_solfege")
        self.assertEqual(snapshot["sessions"], [{"activity_id": "activity-piano-id", "date": "2026-09-07"}])
        self.assertEqual(snapshot["sessions_count"], 1)

    def test_apply_selected_solfege_slot_updates_pending_block_in_snapshot(self) -> None:
        snapshot = {
            "blocks": [
                {
                    "activity_label": "Cours de solfège - niveau 1",
                    "selection_pending": True,
                    "pending_solfege_level": "1",
                    "pending_slot_options": [
                        {
                            "weekday": 1,
                            "weekday_label": "Mardi",
                            "start_time": "17:05",
                            "end_time": "17:35",
                            "location_label": "Online",
                        }
                    ],
                    "weekday": -1,
                    "weekday_label": "Selection a faire",
                    "start_time": "",
                    "end_time": "",
                    "location_label": "Online",
                }
            ]
        }
        selected_slot = {
            "weekday": 1,
            "weekday_label": "Mardi",
            "start_time": "17:05",
            "end_time": "17:35",
            "duration_minutes": 30,
            "location_label": "Online",
            "label": "Mardi 17:05-17:35 · Online",
        }

        updated = _apply_selected_solfege_slot_to_calendar_snapshot(snapshot, selected_slot=selected_slot, language="fr")

        block = updated["blocks"][0]
        assert isinstance(block, dict)
        self.assertFalse(block["selection_pending"])
        self.assertEqual(block["weekday_label"], "Mardi")
        self.assertEqual(block["start_time"], "17:05")
        self.assertEqual(block["end_time"], "17:35")
        self.assertEqual(block["pending_slot_options"], [])
        assert isinstance(updated["solfege"], dict)
        self.assertEqual(updated["solfege"]["selected_slot"]["label"], "Mardi 17:05-17:35 · Online")

    def test_uses_pending_snapshot_options_on_public_quote(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            estimated_solfege_level="2",
            solfege_duration_minutes=45,
            selected_solfege_slot={},
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Cours de solfège - niveau 2",
                        "selection_pending": True,
                        "pending_solfege_level": "2",
                        "pending_slot_options": [
                            {
                                "weekday": 2,
                                "weekday_label": "Mercredi",
                                "start_time": "17:15",
                                "end_time": "18:00",
                                "location_label": "Online",
                                "modality": "ONLINE",
                            }
                        ],
                    }
                ]
            },
        )

        selection = _public_quote_solfege_selection(object(), quote)

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertTrue(selection.pending_selection)
        self.assertTrue(selection.required)
        self.assertEqual(selection.level_code, "2")
        self.assertEqual(len(selection.available_slots), 1)
        self.assertIn("Mercredi", selection.available_slots[0].label)

    def test_falls_back_to_active_rule_when_snapshot_has_no_slot_options(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            estimated_solfege_level="2",
            solfege_duration_minutes=45,
            selected_solfege_slot={},
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Cours de solfège - niveau 2",
                        "selection_pending": True,
                        "pending_solfege_level": "2",
                        "pending_slot_options": [],
                    }
                ]
            },
        )
        fake_rule = SimpleNamespace(
            duration_minutes=45,
            allowed_time_slots=[
                {"weekday": 2, "start_time": "17:15", "end_time": "18:00"},
                {"weekday": 5, "start_time": "10:15", "end_time": "11:00"},
            ],
            allowed_weekdays=[],
            location_id=None,
            modality="ONLINE",
        )

        with patch("app.api.routes.quotes._public_matching_solfege_rule", return_value=fake_rule):
            selection = _public_quote_solfege_selection(object(), quote)

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(len(selection.available_slots), 2)
        self.assertTrue(any("Mercredi 17:15-18:00" in option.label for option in selection.available_slots))
        self.assertTrue(any("Samedi 10:15-11:00" in option.label for option in selection.available_slots))

    def test_extracts_level_from_activity_label_when_quote_has_no_level(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            estimated_solfege_level=None,
            solfege_duration_minutes=None,
            selected_solfege_slot={},
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Cours de solfège - niveau 2",
                        "selection_pending": True,
                        "pending_solfege_level": None,
                        "pending_slot_options": [],
                        "modality": "ONLINE",
                        "location_label": "Online",
                    }
                ]
            },
        )
        fake_rule = SimpleNamespace(
            duration_minutes=45,
            allowed_time_slots=[{"weekday": 2, "start_time": "17:15", "end_time": "18:00"}],
            allowed_weekdays=[],
            location_id=None,
            modality="ONLINE",
        )

        with patch("app.api.routes.quotes._public_matching_solfege_rule", return_value=fake_rule):
            selection = _public_quote_solfege_selection(object(), quote)

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(selection.level_code, "2")
        self.assertEqual(len(selection.available_slots), 1)
        self.assertIn("Mercredi 17:15-18:00", selection.available_slots[0].label)

    def test_keeps_existing_selected_slot_without_requiring_new_choice(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            estimated_solfege_level="2",
            solfege_duration_minutes=45,
            selected_solfege_slot={
                "weekday": 2,
                "weekday_label": "Mercredi",
                "start_time": "17:15",
                "end_time": "18:00",
                "location_label": "Online",
                "modality": "ONLINE",
                "label": "Mercredi 17:15-18:00 · Online",
            },
            calendar_snapshot={"blocks": []},
        )
        fake_rule = SimpleNamespace(
            duration_minutes=45,
            allowed_time_slots=[{"weekday": 5, "start_time": "10:15", "end_time": "11:00"}],
            allowed_weekdays=[],
            location_id=None,
            modality="ONLINE",
        )

        with patch("app.api.routes.quotes._public_matching_solfege_rule", return_value=fake_rule):
            selection = _public_quote_solfege_selection(object(), quote)

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertFalse(selection.required)
        self.assertEqual(selection.selected_label, "Mercredi 17:15-18:00 · Online")
        self.assertTrue(any(option.key == selection.selected_key for option in selection.available_slots))

    def test_stale_selected_slot_does_not_satisfy_new_solfege_level(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            estimated_solfege_level="1",
            solfege_duration_minutes=30,
            selected_solfege_slot={
                "weekday": 2,
                "weekday_label": "Mercredi",
                "start_time": "18:05",
                "end_time": "18:35",
                "duration_minutes": 30,
                "location_label": "Online",
                "modality": "ONLINE",
                "level_code": "1",
            },
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Solfège - niveau 2",
                        "selection_pending": True,
                        "pending_solfege_level": "2",
                        "duration_minutes": 45,
                        "pending_slot_options": [
                            {
                                "weekday": 2,
                                "weekday_label": "Mercredi",
                                "start_time": "18:35",
                                "end_time": "19:20",
                                "location_label": "Online",
                                "modality": "ONLINE",
                                "level_code": "2",
                            }
                        ],
                    }
                ]
            },
        )

        selection = _public_quote_solfege_selection(object(), quote)

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(selection.level_code, "2")
        self.assertEqual(selection.duration_minutes, 45)
        self.assertIsNone(selection.selected_key)
        self.assertTrue(selection.required)
        self.assertEqual(len(selection.available_slots), 1)
        self.assertIn("Mercredi 18:35-19:20", selection.available_slots[0].label)

    def test_infers_selected_slot_from_non_pending_calendar_block(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            estimated_solfege_level=None,
            solfege_duration_minutes=None,
            selected_solfege_slot={},
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Cours de solfège - niveau 1",
                        "selection_pending": False,
                        "pending_slot_options": [],
                        "weekday": 1,
                        "weekday_label": "Mardi",
                        "start_time": "17:05",
                        "end_time": "17:35",
                        "location_id": "90e90b51-e74a-4d94-86e7-7e2f132aa537",
                        "location_label": "Online",
                        "modality": "ONLINE",
                    }
                ]
            },
        )

        selection = _public_quote_solfege_selection(object(), quote)

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertFalse(selection.pending_selection)
        self.assertFalse(selection.required)
        self.assertIsNotNone(selection.selected_key)
        self.assertEqual(selection.selected_label, "Mardi 17:05-17:35 · Online")

    def test_ignores_non_solfege_blocks_when_inferring_selected_slot(self) -> None:
        quote = SimpleNamespace(
            language="fr",
            estimated_solfege_level="1",
            solfege_duration_minutes=None,
            selected_solfege_slot={},
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Cours de piano collectif en presentiel (1h)",
                        "selection_pending": False,
                        "pending_slot_options": [],
                        "weekday": 2,
                        "weekday_label": "Mercredi",
                        "start_time": "15:00",
                        "end_time": "16:00",
                        "location_label": "Rue de Richelieu",
                        "modality": "ONSITE",
                    },
                    {
                        "activity_label": "Cours de solfège - niveau 1",
                        "selection_pending": False,
                        "pending_slot_options": [],
                        "weekday": 1,
                        "weekday_label": "Mardi",
                        "start_time": "17:05",
                        "end_time": "17:35",
                        "location_label": "Online",
                        "modality": "ONLINE",
                    },
                ]
            },
        )

        selection = _public_quote_solfege_selection(object(), quote)

        self.assertIsNotNone(selection)
        assert selection is not None
        self.assertEqual(selection.selected_label, "Mardi 17:05-17:35 · Online")


if __name__ == "__main__":
    unittest.main()
