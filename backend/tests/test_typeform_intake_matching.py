from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.typeform_intakes import (
    _extract_estimated_solfege_level,
    _future_school_year_candidate_configs,
    _intake_list_out_fast,
    _normalize_payload,
    _session_recommendations_have_options,
    _should_try_future_school_year_config,
    _solfege_slot_proposal_from_normalized,
    _stored_messages,
    _typeform_session_option_from_row,
)
from app.services.referrals import referral_category_for_location


class TypeformIntakeMatchingTests(unittest.TestCase):
    def test_intake_list_fast_uses_stored_fields_without_reanalysis(self) -> None:
        config_id = uuid4()
        intake = SimpleNamespace(
            id=uuid4(),
            source_form_id="G8eqpU6H",
            source_response_id="response-1",
            received_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            intake_status="READY_FOR_DRAFT_QUOTE",
            detected_location="Rue d'Assas",
            detected_segment="child",
            detected_school_year="2026-2027",
            related_quote_id=None,
            form_config_id=config_id,
            normalized_payload_json={
                "customer_type": "child",
                "parent_first_name": "Pauline",
                "parent_last_name": "Castelnau-Marchand",
                "parent_email": "pauline@example.test",
                "child_first_name": "Victoria",
                "child_last_name": "De Vilmarest",
            },
            warnings_json=[{"message": "A verifier"}],
            blocking_reasons_json=[],
        )
        config = SimpleNamespace(
            configuration_json={"label": "Paris Enfants 2026-2027"},
            source_code="typeform_paris_child_2026_2027_multisite",
            audience_segment="enfants",
            school_year_label="2026-2027",
        )

        row = _intake_list_out_fast(intake, config=config)

        self.assertEqual(row.source_form_label, "Paris Enfants 2026-2027")
        self.assertEqual(row.prospect_label, "Pauline Castelnau-Marchand")
        self.assertEqual(row.child_label, "Victoria De Vilmarest")
        self.assertEqual(row.warnings, ["A verifier"])
        self.assertEqual(row.blockages, [])

    def test_stored_messages_accepts_legacy_string_entries(self) -> None:
        self.assertEqual(
            _stored_messages(["A verifier", {"message": "A verifier"}, {"message": "Autre"}]),
            ["A verifier", "Autre"],
        )

    def test_normalize_payload_extracts_free_text_referral_and_category(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "requested_location": ["location"],
                },
                "field_labels": {},
            },
            audience_segment="enfants",
            location_code="paris",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"ref": "location", "title": "Lieu du cours souhaité"},
                        "choice": {"label": "Paris 06 - Rue d'Assas"},
                    },
                    {
                        "field": {"id": "referral-free-text", "title": "Famille qui vous a recommandé"},
                        "text": "Famille Martin",
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["referral_referrer_name"], "Famille Martin")
        self.assertEqual(normalized["referral_category"], "PARIS")

    def test_referral_category_distinguishes_home_online_bar_le_duc_and_paris_sites(self) -> None:
        self.assertEqual(referral_category_for_location("Paris 16 - Rue Scheffer"), "PARIS")
        self.assertEqual(referral_category_for_location("Paris 16 - Rue de la Pompe"), "PARIS")
        self.assertEqual(referral_category_for_location("Paris 01 - Rue Richelieu"), "PARIS")
        self.assertEqual(referral_category_for_location("Paris 06 - Rue d'Assas"), "PARIS")
        self.assertEqual(referral_category_for_location("Vidéo Call"), "ONLINE")
        self.assertEqual(referral_category_for_location("Domicile"), "DOMICILE")
        self.assertEqual(referral_category_for_location("Bar-le-Duc"), "BAR_LE_DUC")

    def test_normalize_payload_falls_back_to_creneau_label_for_slot_preferences(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "requested_location": ["requested_location"],
                },
                "field_labels": {},
            },
            audience_segment="eveil",
            location_code="paris_richelieu",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"ref": "requested_location", "title": "Lieu du cours d'initiation"},
                        "choice": {"label": "Paris 1 - Rue de Richelieu"},
                    },
                    {
                        "field": {"id": "94250c22-17f0-47f1-975c-4dbb18656bd8", "title": "Créneau initiation - Rue Richelieu"},
                        "choice": {"label": "Mercredi 15h"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["requested_days"], ["mercredi"])
        self.assertEqual(normalized["requested_times"], ["15:00"])
        self.assertEqual(
            normalized["requested_slot_preferences"],
            [
                {
                    "day": "mercredi",
                    "time": "15:00",
                    "location": "Paris 1 - Rue de Richelieu",
                    "segment": "eveil",
                }
            ],
        )

    def test_normalize_payload_falls_back_to_time_row_labels_when_mapping_is_stale(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "requested_location": ["requested_location"],
                    # Simulate stale stored field ids that no longer match the live Typeform fields.
                    "requested_days": ["obsolete-requested-days-id"],
                    "requested_times": ["obsolete-requested-times-id"],
                    "requested_slot_preferences": ["obsolete-slot-pref-id"],
                },
                "field_labels": {},
            },
            audience_segment="enfants",
            location_code="paris_richelieu",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"ref": "requested_location", "title": "Lieu du cours souhaite"},
                        "choice": {"label": "Paris 01 - Rue Richelieu"},
                    },
                    {
                        "field": {"id": "000338cf-1", "title": "14h-15h"},
                        "choice": {"label": "Mercredi"},
                    },
                    {
                        "field": {"id": "000338cf-2", "title": "15h-16h"},
                        "choice": {"label": "Mercredi"},
                    },
                    {
                        "field": {"id": "000338cf-3", "title": "16h-17h"},
                        "choice": {"label": "Mercredi"},
                    },
                    {
                        "field": {"id": "000338cf-4", "title": "17h-18h"},
                        "choice": {"label": "Mercredi"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["requested_days"], ["mercredi"])
        self.assertEqual(normalized["requested_times"], ["14:00", "15:00", "16:00", "17:00"])
        self.assertEqual(
            normalized["requested_slot_preferences"],
            [
                {
                    "day": "mercredi",
                    "time": "14:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "mercredi",
                    "time": "15:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "mercredi",
                    "time": "16:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "mercredi",
                    "time": "17:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
            ],
        )

    def test_normalize_payload_does_not_mix_solfege_choice_into_main_requested_slots(self) -> None:
        config = SimpleNamespace(
            configuration_json={
                "field_mapping": {
                    "requested_location": ["requested_location"],
                    "requested_days": ["obsolete-requested-days-id"],
                    "requested_times": ["obsolete-requested-times-id"],
                    "requested_slot_preferences": ["obsolete-slot-pref-id"],
                },
                "field_labels": {},
            },
            audience_segment="enfants",
            location_code="paris_richelieu",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"ref": "requested_location", "title": "Lieu du cours souhaité"},
                        "choice": {"label": "Paris 01 - Rue Richelieu"},
                    },
                    {
                        "field": {"id": "course-day", "title": "Quel jour souhaitez vous prendre des cours"},
                        "choice": {"label": "samedi"},
                    },
                    {
                        "field": {"id": "course-saturday-hours", "title": "Horaire de nos cours le samedi"},
                        "choices": {"labels": ["14h", "12h", "11h"]},
                    },
                    {
                        "field": {"id": "solfege-level", "title": "Débutants (5 - 6 ans)"},
                        "choice": {"label": "mercredi - 18h05"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertEqual(normalized["requested_days"], ["samedi"])
        self.assertEqual(normalized["requested_times"], ["14:00", "12:00", "11:00"])
        self.assertEqual(
            normalized["requested_slot_preferences"],
            [
                {
                    "day": "samedi",
                    "time": "14:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "samedi",
                    "time": "12:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
                {
                    "day": "samedi",
                    "time": "11:00",
                    "location": "Paris 01 - Rue Richelieu",
                    "segment": "enfants",
                },
            ],
        )
        self.assertEqual(
            normalized["requested_solfege_slot_preferences"],
            [
                {
                    "day": "mercredi",
                    "time": "18:05",
                    "location": "En ligne",
                    "segment": "enfants",
                }
            ],
        )

    def test_normalize_payload_detects_pass_recup_reenrollment_and_solfege_level(self) -> None:
        config = SimpleNamespace(
            configuration_json={"field_mapping": {}, "field_labels": {}},
            audience_segment="enfants",
            location_code="paris_richelieu",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"id": "reenrollment", "title": "S'agit-il d'une réinscription ?"},
                        "boolean": True,
                    },
                    {
                        "field": {"id": "pass-rec", "title": "Pass Récup'"},
                        "boolean": True,
                    },
                    {
                        "field": {"id": "onsite-solfege", "title": "Cours de solfège en présentiel"},
                        "boolean": True,
                    },
                    {
                        "field": {"id": "solfege-level-estimate", "title": "Estimation du niveau de votre enfant en solfège"},
                        "choice": {"label": "Très bonnes notions de solfège - Niveau 4"},
                    },
                    {
                        "field": {"id": "solfege-slot", "title": "Niveau 4"},
                        "choice": {"label": "jeudi - 18h50"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertTrue(normalized["requested_pass_recup"])
        self.assertTrue(normalized["is_reenrollment"])
        self.assertTrue(normalized["requested_onsite_solfege"])
        self.assertIn("Pass Recup", normalized["requested_products"])
        self.assertIn("Cours de solfege en presentiel", normalized["requested_products"])
        self.assertEqual(normalized["estimated_solfege_level"], "4")
        self.assertEqual(
            normalized["requested_solfege_slot_preferences"],
            [
                {
                    "day": "jeudi",
                    "time": "18:50",
                    "location": "paris_richelieu",
                    "segment": "enfants",
                }
            ],
        )

    def test_normalize_payload_detects_online_solfege_slot_as_requested_product(self) -> None:
        config = SimpleNamespace(
            configuration_json={"field_mapping": {}, "field_labels": {}},
            audience_segment="enfants",
            location_code="paris_assas",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"id": "solfege-online-slot", "title": "Solfège en ligne"},
                        "choice": {"label": "mardi - 17h05"},
                    },
                    {
                        "field": {"id": "solfege-level-estimate", "title": "Estimation du niveau de votre enfant en solfège"},
                        "choice": {"label": "Débutant ou une année de solfège et âge > 7 ans (Niveau 2)"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertFalse(normalized["requested_onsite_solfege"])
        self.assertTrue(normalized["requested_online_solfege"])
        self.assertEqual(normalized["requested_solfege_modality"], "online")
        self.assertIn("Cours de solfege en ligne", normalized["requested_products"])
        self.assertEqual(normalized["estimated_solfege_level"], "2")
        self.assertEqual(
            normalized["requested_solfege_slot_preferences"],
            [
                {
                    "day": "mardi",
                    "time": "17:05",
                    "location": "En ligne",
                    "segment": "enfants",
                }
            ],
        )

    def test_normalize_payload_treats_level_slot_as_online_solfege_when_presentiel_is_false(self) -> None:
        config = SimpleNamespace(
            configuration_json={"field_mapping": {}, "field_labels": {}},
            audience_segment="enfants",
            location_code="paris_assas",
        )
        payload = {
            "form_response": {
                "answers": [
                    {
                        "field": {"id": "onsite-solfege", "title": "Cours de solfège en présentiel"},
                        "boolean": False,
                    },
                    {
                        "field": {"id": "solfege-level-estimate", "title": "Estimation du niveau de votre enfant en solfège"},
                        "choice": {"label": "Très bonnes notions de solfège - Niveau 4"},
                    },
                    {
                        "field": {"id": "solfege-slot", "title": "Niveau 4"},
                        "choice": {"label": "mardi - 17h05"},
                    },
                ]
            }
        }

        normalized, _ = _normalize_payload(payload=payload, config=config)

        self.assertFalse(normalized["requested_onsite_solfege"])
        self.assertTrue(normalized["requested_online_solfege"])
        self.assertEqual(normalized["requested_solfege_modality"], "online")
        self.assertIn("Cours de solfege en ligne", normalized["requested_products"])
        self.assertEqual(
            normalized["requested_solfege_slot_preferences"],
            [
                {
                    "day": "mardi",
                    "time": "17:05",
                    "location": "En ligne",
                    "segment": "enfants",
                }
            ],
        )

    def test_extract_solfege_level_works_with_typeform_slot_without_session_recommendation(self) -> None:
        level = _extract_estimated_solfege_level(
            normalized={
                "estimated_solfege_level": "4",
                "requested_solfege_slot_preferences": [{"day": "mardi", "time": "17:05"}],
                "requested_products": ["Cours de solfege en ligne"],
            },
            session_recommendations=[],
        )

        self.assertEqual(level, "4")

    def test_online_solfege_slot_proposal_does_not_use_main_course_location(self) -> None:
        class FakeScalars:
            def all(self) -> list[object]:
                return [
                    SimpleNamespace(
                        level_code="1",
                        modality="ONLINE",
                        location_id=None,
                        duration_minutes=45,
                        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    )
                ]

        class FakeDb:
            def scalars(self, _stmt: object) -> FakeScalars:
                return FakeScalars()

        proposal = _solfege_slot_proposal_from_normalized(
            FakeDb(),  # type: ignore[arg-type]
            normalized={
                "estimated_solfege_level": "1",
                "requested_solfege_modality": "online",
                "requested_solfege_slot_preferences": [
                    {"day": "mardi", "time": "17:05", "location": "Paris 06 - Rue d'Assas"}
                ],
                "requested_products": ["Cours de solfege en ligne"],
            },
            runtime_context={
                "location_id": str(uuid4()),
                "location_name": "Rue d'Assas",
            },
            session_recommendations=[],
        )

        self.assertEqual(proposal["location_label"], "En ligne")
        self.assertIsNone(proposal["location_id"])
        self.assertNotIn("Assas", str(proposal["label"]))

    def test_option_does_not_mark_other_site_as_preferred_when_location_is_resolved(self) -> None:
        preferred_location_id = uuid4()
        option = _typeform_session_option_from_row(
            session_obj=SimpleNamespace(
                id=uuid4(),
                title="Eveil musical",
                start_at_utc=datetime(2026, 5, 16, 9, 0, tzinfo=timezone.utc),
                end_at_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                timezone="Europe/Paris",
                recurrence_rule="WEEKLY",
                recurrence_group_id=None,
                capacity_max=12,
            ),
            activity=SimpleNamespace(id=uuid4(), name="Eveil musical"),
            location=SimpleNamespace(id=uuid4(), code="BAR_LE_DUC", name="Bar-le-Duc", timezone="Europe/Paris"),
            booked_count=0,
            config=SimpleNamespace(default_location_id=None, location_code="paris_richelieu"),
            requested_location="paris_richelieu",
            resolved_location_id=preferred_location_id,
            requested_slot_preferences=[],
            requested_days=set(),
            requested_times=[],
        )

        self.assertIsNotNone(option)
        assert option is not None
        self.assertNotIn("lieu prefere", option.reasons)

    def test_option_requires_requested_day_when_slot_preferences_are_explicit(self) -> None:
        option = _typeform_session_option_from_row(
            session_obj=SimpleNamespace(
                id=uuid4(),
                title="Eveil musical",
                start_at_utc=datetime(2026, 5, 16, 9, 0, tzinfo=timezone.utc),  # Saturday
                end_at_utc=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                timezone="Europe/Paris",
                recurrence_rule="WEEKLY",
                recurrence_group_id=None,
                capacity_max=12,
            ),
            activity=SimpleNamespace(id=uuid4(), name="Eveil musical"),
            location=SimpleNamespace(id=uuid4(), code="RICHELIEU", name="Rue de Richelieu", timezone="Europe/Paris"),
            booked_count=0,
            config=SimpleNamespace(default_location_id=None, location_code="paris_richelieu"),
            requested_location="Paris 1 - Rue de Richelieu",
            resolved_location_id=uuid4(),
            requested_slot_preferences=[{"day": 2, "time": 900}],  # Wednesday 15:00
            requested_days={2},
            requested_times=[900],
        )

        self.assertIsNone(option)

    def test_should_try_future_school_year_config_when_slots_are_requested_but_no_option_matches(self) -> None:
        should_try = _should_try_future_school_year_config(
            config=SimpleNamespace(source_code="typeform_paris_child_2025_2026_multisite", school_year_label="2025-2026"),
            normalized={
                "requested_slot_preferences": [{"day": "mercredi", "time": "14:00"}],
                "requested_days": ["mercredi"],
                "requested_times": ["14:00"],
            },
            session_recommendations=[],
        )

        self.assertTrue(should_try)

    def test_session_recommendations_have_options_detects_model_options(self) -> None:
        recommendations = [
            SimpleNamespace(
                options=[SimpleNamespace(selection_label="Chaque mercredi · 14:00-15:00")],
                manual_options=[],
            )
        ]

        self.assertTrue(_session_recommendations_have_options(recommendations))

    def test_future_school_year_candidate_configs_prefers_same_family_and_next_year(self) -> None:
        current = SimpleNamespace(
            id=uuid4(),
            source_code="typeform_paris_child_2025_2026_multisite",
            school_year_label="2025-2026",
            location_code="RICHELIEU",
            audience_segment="child",
        )
        next_year = SimpleNamespace(
            id=uuid4(),
            source_code="typeform_paris_child_2026_2027_multisite",
            school_year_label="2026-2027",
            location_code="RICHELIEU",
            audience_segment="child",
            is_active=True,
        )
        wrong_family = SimpleNamespace(
            id=uuid4(),
            source_code="typeform_paris_eveil_2026_2027_multisite",
            school_year_label="2026-2027",
            location_code="RICHELIEU",
            audience_segment="child",
            is_active=True,
        )
        wrong_location = SimpleNamespace(
            id=uuid4(),
            source_code="typeform_paris_child_2026_2027_multisite",
            school_year_label="2026-2027",
            location_code="POMPE",
            audience_segment="child",
            is_active=True,
        )

        class _FakeScalars:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return list(self._rows)

        class _FakeDb:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self, _stmt):
                return _FakeScalars(self._rows)

        rows = [wrong_family, wrong_location, next_year]
        selected = _future_school_year_candidate_configs(_FakeDb(rows), current_config=current)

        self.assertEqual(selected, [next_year])


if __name__ == "__main__":
    unittest.main()
