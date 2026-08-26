from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from uuid import uuid4
from unittest.mock import patch

import jwt
from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.gift_cards import _card_can_be_redeemed, _enforce_lookup_rate_limit
from app.core.config import settings
from app.schemas.gift_card import AdminGiftCardImportRequest, AdminGiftCardStatusRequest
from pydantic import ValidationError
from app.services.gift_cards import (
    decode_gift_card_context,
    encode_gift_card_context,
    gift_card_code_hash,
    gift_card_code_suffix,
    gift_card_external_reference_key,
    normalize_gift_card_code,
)
from app.services.gift_card_imports import MAX_GIFT_CARD_IMPORT_ROWS, parse_gift_card_csv


class GiftCardCodeSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pepper_patch = patch(
            "app.services.gift_cards.settings",
            SimpleNamespace(
                gift_card_code_pepper="test-gift-card-code-pepper-with-at-least-32-characters"
            ),
        )
        self.pepper_patch.start()

    def tearDown(self) -> None:
        self.pepper_patch.stop()

    def test_print_formatting_does_not_change_code_identity(self) -> None:
        raw = "268E-B072-8557-F80C"

        self.assertEqual(normalize_gift_card_code(raw), "268EB0728557F80C")
        self.assertEqual(gift_card_code_hash(raw), gift_card_code_hash("268e b072 8557 f80c"))
        self.assertEqual(gift_card_code_suffix(raw), "8557F80C")

    def test_raw_code_is_not_part_of_hash(self) -> None:
        raw = "268E-B072-8557-F80C"
        digest = gift_card_code_hash(raw)

        self.assertEqual(len(digest), 64)
        self.assertNotIn(normalize_gift_card_code(raw), digest.upper())

    def test_short_codes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            gift_card_code_hash("123")

    def test_missing_or_short_pepper_fails_closed(self) -> None:
        for invalid_pepper in ("", "too-short"):
            with self.subTest(pepper=invalid_pepper):
                with patch(
                    "app.services.gift_cards.settings",
                    SimpleNamespace(gift_card_code_pepper=invalid_pepper),
                ):
                    with self.assertRaisesRegex(RuntimeError, "GIFT_CARD_CODE_PEPPER"):
                        gift_card_code_hash("268E-B072-8557-F80C")


class GiftCardContextTests(unittest.TestCase):
    def test_context_round_trip_contains_only_card_identifier(self) -> None:
        card_id = uuid4()
        token = encode_gift_card_context(card_id)

        self.assertEqual(decode_gift_card_context(token), card_id)
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        self.assertEqual(set(payload), {"scope", "gift_card_id", "iat", "exp"})

    def test_context_rejects_wrong_scope(self) -> None:
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "scope": "PUBLIC_FORMULA_PURCHASE_CONTEXT",
                "gift_card_id": str(uuid4()),
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        with self.assertRaises(HTTPException) as raised:
            decode_gift_card_context(token)
        self.assertEqual(raised.exception.status_code, 400)


class GiftCardLifecycleTests(unittest.TestCase):
    def test_only_active_current_unused_card_can_be_redeemed(self) -> None:
        now = datetime.now(timezone.utc)
        active = SimpleNamespace(
            status="ACTIVE",
            valid_from=now - timedelta(days=1),
            expires_at=now + timedelta(days=1),
            redeemed_at=None,
            subscription_id=None,
        )
        self.assertTrue(_card_can_be_redeemed(active, now=now))

        for change in (
            {"status": "BLOCKED"},
            {"valid_from": now + timedelta(seconds=1)},
            {"expires_at": now},
            {"redeemed_at": now},
            {"subscription_id": uuid4()},
        ):
            candidate = SimpleNamespace(**{**active.__dict__, **change})
            self.assertFalse(_card_can_be_redeemed(candidate, now=now))

    def test_wordpress_reference_is_stable_and_line_specific(self) -> None:
        self.assertEqual(
            gift_card_external_reference_key(
                source="wordpress",
                external_order_ref="485529",
                external_line_ref=None,
            ),
            "WORDPRESS:485529:1",
        )
        self.assertEqual(
            gift_card_external_reference_key(
                source="WORDPRESS",
                external_order_ref="485529",
                external_line_ref="2",
            ),
            "WORDPRESS:485529:2",
        )

    def test_import_schema_normalizes_currency_and_text(self) -> None:
        payload = AdminGiftCardImportRequest(
            code="268E-B072-8557-F80C",
            plan_id=uuid4(),
            currency=" eur ",
            recipient_name="  V  ",
            paid_at=datetime(2026, 8, 26, 15, 30),
        )

        self.assertEqual(payload.currency, "EUR")
        self.assertEqual(payload.recipient_name, "V")
        self.assertEqual(payload.paid_at, datetime(2026, 8, 26, 13, 30, tzinfo=timezone.utc))

    @patch("app.api.routes.gift_cards.consume_rate_limit", side_effect=[(True, 3600), (False, 42)])
    def test_lookup_rate_limit_blocks_repeated_code_attempts(self, rate_limit_mock) -> None:
        request = SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.10"))

        with self.assertRaises(HTTPException) as raised:
            _enforce_lookup_rate_limit(request, code_hash="a" * 64)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.headers, {"Retry-After": "42"})
        self.assertEqual(rate_limit_mock.call_count, 2)

    def test_admin_status_schema_cannot_mark_a_card_redeemed(self) -> None:
        with self.assertRaises(ValidationError):
            AdminGiftCardStatusRequest(status="REDEEMED")


class GiftCardCsvPreviewTests(unittest.TestCase):
    def test_paid_wordpress_row_is_ready_for_database_checks(self) -> None:
        csv_content = (
            "Code de la carte-cadeau;Numéro de commande;État de la commande;"
            "Date de paiement;Nom de l’élément;Valeur de l'offre TTC;Prix payé TTC\n"
            "268E-B072-8557-F80C;485529;Terminée;2026-08-26 15:30;"
            "Carte cadeau - Apprenez votre 1er morceau;150;150\n"
        ).encode()

        rows = parse_gift_card_csv(csv_content)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].code_suffix, "8557F80C")
        self.assertEqual(rows[0].external_order_ref, "485529")
        self.assertEqual(rows[0].face_value_ttc, Decimal("150.00"))
        self.assertEqual(rows[0].purchase_price_ttc, Decimal("150.00"))
        self.assertEqual(rows[0].errors, ())

    def test_unpaid_or_incomplete_row_is_blocked(self) -> None:
        csv_content = (
            "code,order_id,status,paid_at,face_value_ttc,purchase_price_ttc\n"
            "268E-B072-8557-F80C,485529,pending,,150,125\n"
        ).encode()

        row = parse_gift_card_csv(csv_content)[0]

        self.assertIn("Le statut de la commande ne confirme pas le paiement.", row.errors)
        self.assertIn("Date de paiement manquante.", row.errors)

    def test_missing_code_and_amounts_are_reported_without_guessing(self) -> None:
        csv_content = "order_id,status,paid_at\n485529,completed,2026-08-26\n".encode()

        row = parse_gift_card_csv(csv_content)[0]

        self.assertIsNone(row.code)
        self.assertIsNone(row.face_value_ttc)
        self.assertIsNone(row.purchase_price_ttc)
        self.assertGreaterEqual(len(row.errors), 3)

    def test_import_row_limit_is_enforced(self) -> None:
        header = "code,order_id,status,paid_at,face_value_ttc,purchase_price_ttc\n"
        data = "\n".join(
            f"AAAA-BBBB-CCCC-{index:04X},{index},completed,2026-08-26,150,150"
            for index in range(MAX_GIFT_CARD_IMPORT_ROWS + 1)
        )

        with self.assertRaisesRegex(ValueError, "limité"):
            parse_gift_card_csv(f"{header}{data}\n".encode())


if __name__ == "__main__":
    unittest.main()
