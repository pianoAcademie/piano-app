from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.quotes.quote_documents import (
    _line_groups,
    _pass_recup_compact_notice_markup,
    _solfege_pending_block_info,
)


class QuoteDocumentMarkupTests(unittest.TestCase):
    def test_pass_recup_compact_pdf_markup_is_reportlab_compatible(self) -> None:
        markup = _pass_recup_compact_notice_markup(language="fr", pdf_compatible=True)
        markup = markup.replace("<p>", "").replace("</p>", "")

        paragraph = Paragraph(markup, getSampleStyleSheet()["BodyText"])

        self.assertIsNotNone(paragraph)
        self.assertIn("<font", markup)
        self.assertNotIn("<span", markup)

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


if __name__ == "__main__":
    unittest.main()
