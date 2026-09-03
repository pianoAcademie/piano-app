from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import (
    _quote_admin_hold_note,
    _quote_meta_without_admin_hold_note,
    _set_quote_admin_hold_note,
)


class QuoteAdminHoldNoteTests(unittest.TestCase):
    def test_note_is_trimmed_and_preserves_other_metadata(self) -> None:
        quote = SimpleNamespace(meta={"language": "fr", "document_binding_id": "binding-id"})

        changed = _set_quote_admin_hold_note(quote, "  Attendre l'ouverture du second creneau.  ")

        self.assertTrue(changed)
        self.assertEqual(_quote_admin_hold_note(quote.meta), "Attendre l'ouverture du second creneau.")
        self.assertEqual(quote.meta["language"], "fr")
        self.assertEqual(quote.meta["document_binding_id"], "binding-id")

    def test_resolving_note_removes_only_hold_metadata(self) -> None:
        quote = SimpleNamespace(meta={"admin_hold_note": "En attente", "language": "en"})

        changed = _set_quote_admin_hold_note(quote, None)

        self.assertTrue(changed)
        self.assertIsNone(_quote_admin_hold_note(quote.meta))
        self.assertNotIn("admin_hold_note", quote.meta)
        self.assertEqual(quote.meta["language"], "en")

    def test_unchanged_note_is_idempotent(self) -> None:
        quote = SimpleNamespace(meta={"admin_hold_note": "En attente"})

        changed = _set_quote_admin_hold_note(quote, "En attente")

        self.assertFalse(changed)

    def test_note_is_limited_to_schema_maximum(self) -> None:
        quote = SimpleNamespace(meta={})

        _set_quote_admin_hold_note(quote, "x" * 4500)

        self.assertEqual(len(_quote_admin_hold_note(quote.meta) or ""), 4000)

    def test_public_or_duplicated_metadata_excludes_internal_note(self) -> None:
        meta = {
            "admin_hold_note": "Information strictement interne",
            "invoice_recipient_override": {
                "enabled": True,
                "company_name": "Société test",
                "billing_address": "1 rue du Test",
            },
            "language": "fr",
        }

        sanitized = _quote_meta_without_admin_hold_note(meta)

        self.assertNotIn("admin_hold_note", sanitized)
        self.assertNotIn("invoice_recipient_override", sanitized)
        self.assertEqual(sanitized["language"], "fr")
        self.assertIn("admin_hold_note", meta)


if __name__ == "__main__":
    unittest.main()
