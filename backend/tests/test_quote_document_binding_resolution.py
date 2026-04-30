from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.quotes import (
    _choose_primary_quote_activity_for_documents,
    _pick_best_document_binding,
)


class QuoteDocumentBindingResolutionTests(unittest.TestCase):
    def test_specific_binding_beats_generic_even_if_priority_is_lower(self) -> None:
        quote_type_id = uuid4()
        activity_id = uuid4()
        generic = SimpleNamespace(
            activity_id=None,
            quote_type_id=None,
            activity_family=None,
            prospect_type="child",
            context_type="acquisition",
            language="fr",
            currency="EUR",
            priority=1,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        specific = SimpleNamespace(
            activity_id=activity_id,
            quote_type_id=quote_type_id,
            activity_family=None,
            prospect_type="child",
            context_type="acquisition",
            language="fr",
            currency="EUR",
            priority=999,
            created_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
        )

        picked = _pick_best_document_binding([generic, specific])

        self.assertIs(picked, specific)

    def test_more_specific_quote_type_binding_beats_family_only_binding(self) -> None:
        family_only = SimpleNamespace(
            activity_id=None,
            quote_type_id=None,
            activity_family="piano_class",
            prospect_type="child",
            context_type=None,
            language="fr",
            currency="EUR",
            priority=10,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        family_and_type = SimpleNamespace(
            activity_id=None,
            quote_type_id=uuid4(),
            activity_family="piano_class",
            prospect_type="child",
            context_type=None,
            language="fr",
            currency="EUR",
            priority=100,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 3, tzinfo=timezone.utc),
        )

        picked = _pick_best_document_binding([family_only, family_and_type])

        self.assertIs(picked, family_and_type)

    def test_primary_quote_activity_prefers_non_solfege_activity(self) -> None:
        solfege = SimpleNamespace(
            id=uuid4(),
            code="SOLFEGE_ONLINE_30M",
            name="Cours de solfege - niveau 1",
            service_code="SOLFEGE",
        )
        piano = SimpleNamespace(
            id=uuid4(),
            code="PIANO_GROUP_ONSITE_1H",
            name="Cours de piano collectif en presentiel",
            service_code="PIANO_CLASS",
        )

        picked = _choose_primary_quote_activity_for_documents([solfege, piano])

        self.assertIs(picked, piano)


if __name__ == "__main__":
    unittest.main()
