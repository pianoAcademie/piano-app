from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.api.routes.quotes import _country_vat_rate_for_quote, _quote_recipient_country
from app.schemas.quote import QuoteLineIn
from app.services.pricing import resolve_vat_rate


class QuoteCountryVatTests(unittest.TestCase):
    def test_recipient_country_prefers_client_residence(self) -> None:
        client = SimpleNamespace(residence_country="SA", address_country="FR")

        self.assertEqual(_quote_recipient_country(client=client, prospect=None), "SA")

    def test_recipient_country_recognizes_saudi_prospect_label(self) -> None:
        prospect = SimpleNamespace(meta={"parent_country": "Arabie saoudite"})

        self.assertEqual(_quote_recipient_country(client=None, prospect=prospect), "SA")

    def test_country_rate_uses_saudi_zero_vat_rule(self) -> None:
        db = MagicMock()
        db.scalar.return_value = SimpleNamespace(service_code="PIANO_CLASS")
        exact_result = MagicMock()
        exact_result.first.return_value = SimpleNamespace(vat_rate=Decimal("0.00"))
        db.scalars.return_value = exact_result
        line = QuoteLineIn(
            line_category="service",
            activity_id=uuid4(),
            title="Cours de piano",
            unit_price_ttc=Decimal("100.00"),
        )

        rate = _country_vat_rate_for_quote(
            db,
            country="SA",
            lines=[line],
            on_date=date(2026, 7, 31),
        )

        self.assertEqual(rate, Decimal("0.000"))

    def test_country_rate_does_not_override_french_quotes(self) -> None:
        db = MagicMock()

        rate = _country_vat_rate_for_quote(
            db,
            country="FR",
            lines=[],
            on_date=date(2026, 7, 31),
        )

        self.assertIsNone(rate)
        db.scalar.assert_not_called()
        db.scalars.assert_not_called()

    def test_new_saudi_service_codes_still_default_to_zero(self) -> None:
        db = MagicMock()
        exact_result = MagicMock()
        exact_result.first.return_value = None
        db.scalars.return_value = exact_result

        rate = resolve_vat_rate(
            db,
            country="SA",
            service_code="FUTURE_ONLINE_SERVICE",
            on_date=date(2026, 7, 31),
        )

        self.assertEqual(rate, Decimal("0.00"))
        self.assertEqual(db.scalars.call_count, 1)


if __name__ == "__main__":
    unittest.main()
