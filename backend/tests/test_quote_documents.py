from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.quotes.quote_documents import (
    _calendar_snapshot_with_planning_sessions,
    _calendar_snapshot_with_current_solfege_block,
    _check_payment_instruction_lines,
    _current_solfege_document_info,
    _line_groups,
    _line_matches_end_year_concert,
    _pass_recup_compact_notice_markup,
    _planning_blocks_table_html,
    _quote_template_allows_end_year_concert,
    _solfege_pending_block_info,
)


class QuoteDocumentMarkupTests(unittest.TestCase):
    def test_calendar_snapshot_hydrates_missing_block_sessions_from_planning(self) -> None:
        activity_id = uuid4()
        location_id = uuid4()
        session_id = uuid4()
        recurrence_id = uuid4()
        fake_db = SimpleNamespace(
            execute=lambda _query: SimpleNamespace(
                all=lambda: [
                    (
                        SimpleNamespace(
                            id=session_id,
                            course_type_id=activity_id,
                            location_id=location_id,
                            status="SCHEDULED",
                            start_at_utc=datetime(2026, 10, 7, 16, 5, tzinfo=timezone.utc),
                            end_at_utc=datetime(2026, 10, 7, 16, 35, tzinfo=timezone.utc),
                            timezone="Europe/Paris",
                            recurrence_group_id=recurrence_id,
                        ),
                        SimpleNamespace(id=activity_id, name="Cours de solfège - Niveau 1", mode="ONLINE"),
                        SimpleNamespace(id=location_id, name="Online", timezone="Europe/Paris", is_online=True),
                    )
                ]
            )
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours de solfège - Niveau 1",
                    "location_label": "En ligne",
                    "weekday": 2,
                    "weekday_label": "Mercredi",
                    "start_date": "2026-09-01",
                    "end_date": "2027-08-31",
                    "start_time": "18:05",
                    "end_time": "18:35",
                    "modality": "ONLINE",
                    "selection_pending": False,
                }
            ],
            "sessions": [],
        }

        hydrated = _calendar_snapshot_with_planning_sessions(fake_db, snapshot)

        self.assertEqual(hydrated["sessions_count"], 1)
        self.assertEqual(hydrated["sessions"][0]["date"], "2026-10-07")
        self.assertEqual(hydrated["sessions"][0]["activity_label"], "Cours de solfège - Niveau 1")
        self.assertEqual(hydrated["sessions"][0]["modality"], "ONLINE")

    def test_pass_recup_compact_pdf_markup_is_reportlab_compatible(self) -> None:
        markup = _pass_recup_compact_notice_markup(language="fr", pdf_compatible=True)
        markup = markup.replace("<p>", "").replace("</p>", "")

        paragraph = Paragraph(markup, getSampleStyleSheet()["BodyText"])

        self.assertIsNotNone(paragraph)
        self.assertIn("<font", markup)
        self.assertNotIn("<span", markup)

    def test_end_year_concert_line_match_detects_billed_option(self) -> None:
        line = SimpleNamespace(
            title="Concert de fin d’année",
            code="CONCERT_FIN_ANNEE",
            line_type="item",
            line_category="product",
            master_item_type="product",
        )

        self.assertTrue(_line_matches_end_year_concert(line))

    def test_end_year_concert_template_gate_uses_meta(self) -> None:
        enabled_quote = SimpleNamespace(
            meta={"end_year_concert_option_mode": "enabled"},
            quote_template_id=None,
            quote_template_version_id=None,
        )
        regular_quote = SimpleNamespace(meta={}, quote_template_id=None, quote_template_version_id=None)

        self.assertTrue(_quote_template_allows_end_year_concert(db=None, quote=enabled_quote))
        self.assertFalse(_quote_template_allows_end_year_concert(db=None, quote=regular_quote))

    def test_solfege_pending_info_detects_accented_labels_and_keeps_slot_proposals(self) -> None:
        snapshot = {
            "blocks": [
                {
                    "activity_label": "Cours de solfège - niveau 2",
                    "location_label": "Online",
                    "weekday": -1,
                    "selection_pending": True,
                    "pending_slot_options": [
                        {
                            "weekday_label": "Mercredi",
                            "start_time": "17:15",
                            "end_time": "18:00",
                            "location_label": "Online",
                            "modality": "ONLINE",
                        },
                        {
                            "weekday_label": "Samedi",
                            "start_time": "10:15",
                            "end_time": "11:00",
                            "location_label": "Online",
                            "modality": "ONLINE",
                        },
                    ],
                }
            ]
        }

        info = _solfege_pending_block_info(snapshot, language="fr")

        self.assertTrue(info["has_pending_selection"])
        self.assertEqual(info["level_code"], "2")
        self.assertGreaterEqual(len(info["slot_labels"]), 2)
        self.assertTrue(any("Mercredi" in label for label in info["slot_labels"]))
        self.assertTrue(any("Samedi" in label for label in info["slot_labels"]))

    def test_solfege_pending_info_falls_back_to_rule_slots_when_snapshot_has_none(self) -> None:
        snapshot = {
            "blocks": [
                {
                    "activity_label": "Cours de solfège - niveau 2",
                    "location_label": "Online",
                    "location_id": None,
                    "weekday": -1,
                    "selection_pending": True,
                    "pending_solfege_level": "2",
                    "modality": "ONLINE",
                    "pending_slot_options": [],
                }
            ]
        }
        fake_rule = SimpleNamespace(
            allowed_time_slots=[
                {"weekday": 2, "start_time": "17:15", "end_time": "18:00"},
                {"weekday": 5, "start_time": "10:15", "end_time": "11:00"},
            ],
            allowed_weekdays=[],
            location_id=None,
            modality="ONLINE",
            created_at=None,
        )

        with patch(
            "app.services.quotes.quote_documents._matching_solfege_rule_for_pending_block",
            return_value=fake_rule,
        ):
            info = _solfege_pending_block_info(snapshot, db=object(), language="fr")

        self.assertTrue(info["has_pending_selection"])
        self.assertTrue(any("Mercredi 17:15-18:00" in label for label in info["slot_labels"]))
        self.assertTrue(any("Samedi 10:15-11:00" in label for label in info["slot_labels"]))

    def test_planning_blocks_table_uses_selected_solfege_slot_when_pending_block_was_chosen(self) -> None:
        snapshot = {
            "blocks": [
                {
                    "activity_label": "Cours de solfège - niveau 1",
                    "location_label": "Online",
                    "weekday": -1,
                    "weekday_label": "Selection a faire",
                    "start_time": "",
                    "end_time": "",
                    "duration_minutes": 30,
                    "selection_pending": True,
                    "pending_solfege_level": "1",
                    "pending_slot_options": [
                        {
                            "weekday_label": "Mardi",
                            "start_time": "17:05",
                            "end_time": "17:35",
                            "location_label": "Online",
                        }
                    ],
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

        html, count = _planning_blocks_table_html(
            snapshot,
            selected_solfege_slot=selected_slot,
            language="fr",
        )

        self.assertEqual(count, 1)
        self.assertIn("Mardi", html)
        self.assertIn("17:05 - 17:35", html)
        self.assertNotIn("à choisir", html)

    def test_current_solfege_document_info_prefers_saved_line_and_planning_over_stale_quote_fields(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            activity_id=activity_id,
            title="Solfège - Niveau 2",
            description="Cours de solfège en ligne",
            code="SOLFEGE_NIVEAU_2",
            duration_minutes=45,
            meta={},
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(activity_id),
                    "activity_label": "Cours de solfège - Niveau 2",
                    "location_label": "Online",
                    "weekday": 3,
                    "weekday_label": "Jeudi",
                    "start_time": "18:50",
                    "end_time": "19:35",
                    "duration_minutes": 45,
                    "selection_pending": False,
                    "pending_solfege_level": "2",
                    "modality": "ONLINE",
                }
            ]
        }
        stale_selected_slot = {
            "weekday": 2,
            "weekday_label": "Mercredi",
            "start_time": "18:05",
            "end_time": "18:35",
            "duration_minutes": 30,
            "location_label": "Online",
            "level_code": "1",
        }

        info = _current_solfege_document_info(
            lines=[line],
            calendar_snapshot=snapshot,
            quote_selected_slot=stale_selected_slot,
            quote_level="1",
            quote_duration_minutes=30,
            language="fr",
        )

        self.assertEqual(info["level_code"], "2")
        self.assertEqual(info["duration_minutes"], 45)
        self.assertEqual(info["selected_slot"]["weekday_label"], "Jeudi")
        self.assertEqual(info["selected_slot"]["start_time"], "18:50")
        self.assertIn("cours en ligne", info["selected_slot"]["label"].lower())

    def test_current_solfege_document_info_matches_same_level_when_activity_ids_differ(self) -> None:
        line_activity_id = uuid4()
        planning_activity_id = uuid4()
        line = SimpleNamespace(
            activity_id=line_activity_id,
            title="Cours de solfège en ligne - niveau 4",
            description="Cours de solfège en ligne",
            code="SOLFEGE_NIVEAU_4",
            duration_minutes=45,
            meta={},
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(planning_activity_id),
                    "activity_label": "Solfège niveau 4",
                    "location_label": "Online",
                    "weekday": 3,
                    "weekday_label": "Jeudi",
                    "start_time": "18:50",
                    "end_time": "19:35",
                    "duration_minutes": 45,
                    "selection_pending": False,
                    "pending_solfege_level": "4",
                    "modality": "ONLINE",
                }
            ]
        }

        info = _current_solfege_document_info(
            lines=[line],
            calendar_snapshot=snapshot,
            quote_selected_slot={},
            quote_level="4",
            quote_duration_minutes=45,
            language="fr",
        )

        self.assertTrue(info["has_current_solfege"])
        self.assertEqual(info["level_code"], "4")
        self.assertEqual(info["selected_slot"]["weekday_label"], "Jeudi")
        self.assertEqual(info["selected_slot"]["start_time"], "18:50")

    def test_current_solfege_document_info_ignores_stale_quote_fields_without_current_solfege(self) -> None:
        stale_selected_slot = {
            "weekday": 2,
            "weekday_label": "Mercredi",
            "start_time": "18:05",
            "end_time": "18:35",
            "duration_minutes": 30,
            "location_label": "Online",
            "level_code": "1",
        }

        info = _current_solfege_document_info(
            lines=[],
            calendar_snapshot={
                "blocks": [
                    {
                        "activity_label": "Cours de piano collectif en présentiel (1h)",
                        "location_label": "Rue de Richelieu",
                        "weekday": 5,
                        "weekday_label": "Samedi",
                        "start_time": "11:00",
                        "end_time": "12:00",
                        "duration_minutes": 60,
                    }
                ]
            },
            quote_selected_slot=stale_selected_slot,
            quote_level="1",
            quote_duration_minutes=30,
            language="fr",
        )

        self.assertFalse(info["has_current_solfege"])
        self.assertEqual(info["level_code"], "")
        self.assertIsNone(info["duration_minutes"])
        self.assertEqual(info["selected_slot"], {})

    def test_current_solfege_block_is_added_to_planning_table_when_snapshot_lacks_it(self) -> None:
        activity_id = uuid4()
        line = SimpleNamespace(
            activity_id=activity_id,
            title="Solfège - Niveau 1",
            description="Cours de solfège en ligne",
            code="SOLFEGE_NIVEAU_1",
            duration_minutes=30,
            meta={},
        )
        snapshot = {
            "blocks": [
                {
                    "activity_id": str(uuid4()),
                    "activity_label": "Cours de piano collectif en présentiel (1h)",
                    "location_label": "Rue d Assas",
                    "weekday": 1,
                    "weekday_label": "Mardi",
                    "start_time": "17:00",
                    "end_time": "18:00",
                    "duration_minutes": 60,
                    "selection_pending": False,
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
            "level_code": "1",
            "modality": "ONLINE",
        }

        snapshot = _calendar_snapshot_with_current_solfege_block(
            snapshot,
            lines=[line],
            selected_solfege_slot=selected_slot,
            language="fr",
        )
        html, count = _planning_blocks_table_html(snapshot, language="fr")

        self.assertEqual(count, 2)
        self.assertIn("Cours de piano collectif", html)
        self.assertIn("Cours de solfège en ligne - niveau 1", html)
        self.assertIn("à choisir", html)

    def test_line_groups_route_service_products_to_other_fees(self) -> None:
        product_id = uuid4()
        line = SimpleNamespace(
            line_type="item",
            master_item_type="product",
            title="Frais de coordination",
            code="FEE_COORDINATION",
            line_category="product",
            product_id=product_id,
            kit_id=None,
        )

        services, products, kits, adjustments, other_fees = _line_groups([line], service_product_ids={product_id})

        self.assertEqual(services, [])
        self.assertEqual(products, [])
        self.assertEqual(kits, [])
        self.assertEqual(adjustments, [])
        self.assertEqual(other_fees, [line])

    def test_check_payment_instructions_use_piano_academie_payee(self) -> None:
        lines = _check_payment_instruction_lines(
            payment_method_label="Cheque",
            schedule=[],
            legal_entity_name="Piano Academie SAS",
            has_deposit=False,
            language="fr",
        )

        self.assertIn("à l’ordre de PIANO ACADEMIE", " ".join(lines))
        self.assertTrue(any("signer vos chèques" in line or "signez vos chèques" in line.lower() for line in lines))
        self.assertTrue(any("1 rue de Richelieu, 75001 PARIS" in line for line in lines))
        self.assertFalse(any("acompte" in line.lower() for line in lines))
        self.assertFalse(any("l’ensemble des chèques" in line for line in lines))

    def test_check_payment_instructions_use_services_payee_and_deposit_card_notice(self) -> None:
        lines = _check_payment_instruction_lines(
            payment_method_label="",
            schedule=[{"payment_method": "Chèque"}, {"payment_method": "Chèque"}],
            legal_entity_name="Piano Academie Services SAS",
            has_deposit=True,
            deposit_amount_ttc=Decimal("200.00"),
            currency="EUR",
            language="fr",
        )

        joined = " ".join(lines)
        self.assertIn("à l’ordre de PIANO ACADEMIE SERVICES", joined)
        self.assertIn("L’acompte de 200,00 EUR", joined)
        self.assertIn("doit être réglé par carte bancaire", joined)
        self.assertIn("avec le lien de paiement", joined)
        self.assertIn("l’ensemble des chèques doit être envoyé avant le démarrage des cours", joined)
        self.assertNotIn("Lorsqu’un acompte est demandé", joined)


if __name__ == "__main__":
    unittest.main()
