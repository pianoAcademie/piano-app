from __future__ import annotations

from pathlib import Path
import sys
import unittest

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.quotes.quote_documents import (
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


if __name__ == "__main__":
    unittest.main()
