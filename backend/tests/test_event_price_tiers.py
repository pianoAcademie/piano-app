from __future__ import annotations

import unittest
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.api.routes.events import (
    _create_event_checkout,
    _registration_price_tier,
    _valid_event_image_signature,
    get_public_event_image,
    upload_admin_event_image,
)
from app.schemas.event import SchoolEventPublicRegistrationCreateRequest, SchoolEventRegistrationCreateRequest


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Db:
    def __init__(self, tiers):
        self._tiers = tiers

    def scalars(self, _statement):
        return _ScalarResult(self._tiers)

    def commit(self):
        return None


class EventPriceTierTests(unittest.TestCase):
    def test_event_visual_signature_validation(self) -> None:
        self.assertTrue(_valid_event_image_signature(b"\x89PNG\r\n\x1a\ncontent", ".png"))
        self.assertTrue(_valid_event_image_signature(b"\xff\xd8\xffcontent", ".jpg"))
        self.assertTrue(_valid_event_image_signature(b"RIFF1234WEBPcontent", ".webp"))
        self.assertFalse(_valid_event_image_signature(b"not-an-image", ".png"))

    def test_event_visual_upload_is_publicly_readable(self) -> None:
        event_id = uuid4()
        event = SimpleNamespace(id=event_id, image_url=None, updated_at=None)

        class _ImageDb:
            def get(self, _model, requested_id):
                return event if requested_id == event_id else None

            def commit(self):
                return None

        upload = UploadFile(
            filename="affiche.png",
            file=BytesIO(b"\x89PNG\r\n\x1a\ncontent"),
            headers=Headers({"content-type": "image/png"}),
        )
        with TemporaryDirectory() as directory, patch(
            "app.api.routes.events.EVENT_IMAGE_UPLOAD_DIR", Path(directory)
        ):
            result = asyncio.run(upload_admin_event_image(event_id, upload, _ImageDb(), None))
            response = get_public_event_image(result.storage_key)
            self.assertTrue(Path(response.path).is_file())
            self.assertEqual(result.image_url, f"/api/events/images/{result.storage_key}")

    def test_legacy_single_price_remains_available(self) -> None:
        event = SimpleNamespace(id=uuid4(), price_ttc=Decimal("19.90"))
        price, tier = _registration_price_tier(_Db([]), event=event, requested_tier_id=None)
        self.assertEqual(price, Decimal("19.90"))
        self.assertIsNone(tier)

    def test_multiple_tiers_require_a_client_choice(self) -> None:
        event = SimpleNamespace(id=uuid4(), price_ttc=Decimal("0"))
        tiers = [SimpleNamespace(id=uuid4(), price_ttc=Decimal("8")), SimpleNamespace(id=uuid4(), price_ttc=Decimal("15"))]
        with self.assertRaises(HTTPException) as context:
            _registration_price_tier(_Db(tiers), event=event, requested_tier_id=None)
        self.assertEqual(context.exception.status_code, 422)

    def test_selected_tier_price_is_snapshotted(self) -> None:
        event = SimpleNamespace(id=uuid4(), price_ttc=Decimal("0"))
        selected = SimpleNamespace(id=uuid4(), price_ttc=Decimal("12.50"))
        other = SimpleNamespace(id=uuid4(), price_ttc=Decimal("20"))
        price, tier = _registration_price_tier(
            _Db([selected, other]), event=event, requested_tier_id=selected.id
        )
        self.assertEqual(price, Decimal("12.50"))
        self.assertIs(tier, selected)

    def test_private_tier_is_rejected_for_online_booking(self) -> None:
        event = SimpleNamespace(id=uuid4(), price_ttc=Decimal("0"))
        private_tier = SimpleNamespace(
            id=uuid4(),
            price_ttc=Decimal("0"),
            is_online_booking_enabled=False,
        )
        with self.assertRaises(HTTPException) as context:
            _registration_price_tier(
                _Db([private_tier]),
                event=event,
                requested_tier_id=private_tier.id,
            )
        self.assertEqual(context.exception.status_code, 422)

    def test_private_tier_remains_available_for_admin_booking(self) -> None:
        event = SimpleNamespace(id=uuid4(), price_ttc=Decimal("0"))
        private_tier = SimpleNamespace(
            id=uuid4(),
            price_ttc=Decimal("0"),
            is_online_booking_enabled=False,
        )
        price, tier = _registration_price_tier(
            _Db([private_tier]),
            event=event,
            requested_tier_id=private_tier.id,
            allow_private_tiers=True,
        )
        self.assertEqual(price, Decimal("0.00"))
        self.assertIs(tier, private_tier)

    def test_participants_can_choose_different_tiers(self) -> None:
        slot_id = uuid4()
        adult_id, child_id = uuid4(), uuid4()
        adult_tier_id, child_tier_id = uuid4(), uuid4()
        payload = SchoolEventRegistrationCreateRequest.model_validate(
            {
                "slot_id": str(slot_id),
                "participant_user_ids": [str(adult_id), str(child_id)],
                "participant_price_tier_ids": {
                    str(adult_id): str(adult_tier_id),
                    str(child_id): str(child_tier_id),
                },
            }
        )
        self.assertEqual(payload.participant_price_tier_ids[adult_id], adult_tier_id)
        self.assertEqual(payload.participant_price_tier_ids[child_id], child_tier_id)

    def test_connected_booking_accepts_guests_with_distinct_prices(self) -> None:
        adult_tier_id, child_tier_id = uuid4(), uuid4()
        payload = SchoolEventRegistrationCreateRequest.model_validate(
            {
                "slot_id": str(uuid4()),
                "guest_tickets": [
                    {"participant_name": "Alice Martin", "price_tier_id": str(adult_tier_id)},
                    {"participant_name": "Léa Martin", "price_tier_id": str(child_tier_id)},
                ],
            }
        )
        self.assertEqual(payload.guest_tickets[0].participant_name, "Alice Martin")
        self.assertEqual(payload.guest_tickets[0].price_tier_id, adult_tier_id)
        self.assertEqual(payload.guest_tickets[1].price_tier_id, child_tier_id)

    def test_public_booking_accepts_named_tickets_with_distinct_prices(self) -> None:
        performer_tier_id, adult_tier_id = uuid4(), uuid4()
        payload = SchoolEventPublicRegistrationCreateRequest.model_validate(
            {
                "request_id": str(uuid4()),
                "slot_id": str(uuid4()),
                "first_name": "Alice",
                "last_name": "Martin",
                "email": "Alice@example.com",
                "language": "fr-FR",
                "terms_accepted": True,
                "tickets": [
                    {"participant_name": "Léa Martin", "price_tier_id": str(performer_tier_id)},
                    {"participant_name": "Alice Martin", "price_tier_id": str(adult_tier_id)},
                ],
            }
        )
        self.assertEqual(payload.email, "alice@example.com")
        self.assertEqual(payload.tickets[0].price_tier_id, performer_tier_id)
        self.assertEqual(payload.tickets[1].price_tier_id, adult_tier_id)

    def test_public_booking_requires_privacy_consent(self) -> None:
        with self.assertRaises(ValueError):
            SchoolEventPublicRegistrationCreateRequest.model_validate(
                {
                    "request_id": str(uuid4()),
                    "slot_id": str(uuid4()),
                    "first_name": "Alice",
                    "last_name": "Martin",
                    "email": "alice@example.com",
                    "terms_accepted": False,
                    "tickets": [{"participant_name": "Léa Martin"}],
                }
            )

    def test_public_online_checkout_uses_public_contact_without_client_id(self) -> None:
        event = SimpleNamespace(id=uuid4(), currency="EUR", title_fr="Concert", slug="concert")
        slot = SimpleNamespace(id=uuid4())
        row = SimpleNamespace(
            group_id=uuid4(),
            total_ttc_snapshot=Decimal("20.00"),
            status=None,
            payment_provider=None,
            payment_reference=None,
            payment_checkout_url=None,
            payment_hold_expires_at=None,
        )
        checkout = SimpleNamespace(
            success=True,
            checkout_url="https://pay.example/checkout",
            provider=SimpleNamespace(value="STRIPE"),
            provider_reference="evt_public_1",
            message="ok",
        )
        with (
            patch("app.api.routes.events.resolve_frontend_base_url", return_value="https://app.example"),
            patch("app.api.routes.events.resolve_webhook_secret", return_value="secret"),
            patch("app.api.routes.events.with_webhook_secret", side_effect=lambda url, _secret: url),
            patch("app.api.routes.events.create_checkout_session", return_value=checkout) as create_checkout,
        ):
            url = _create_event_checkout(
                _Db([]),
                event=event,
                slot=slot,
                booker=None,
                rows=[row],
                public_email="alice@example.com",
                public_first_name="Alice",
                public_last_name="Martin",
            )
        request = create_checkout.call_args.args[1]
        self.assertEqual(url, "https://pay.example/checkout")
        self.assertEqual(request.customer_email, "alice@example.com")
        self.assertEqual(request.metadata["public_booking"], "true")
        self.assertNotIn("client_id", request.metadata)
        self.assertGreater(row.payment_hold_expires_at, datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
