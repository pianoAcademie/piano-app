from __future__ import annotations

import json
import hashlib
import hmac
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs

from app.services import payment_checkout, psp_gateway
from app.services.payment_checkout import CheckoutCreateRequest
from app.services.payment_provider import PaymentProvider, detect_provider_from_reference
from app.services.psp_gateway import RecurringChargeRequest, StripeGateway
from app.api.routes.payments_public import _extract_reference, _verify_stripe_webhook_signature


class _Response:
    def __init__(self, payload: dict[str, object], *, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _checkout_payload() -> CheckoutCreateRequest:
    return CheckoutCreateRequest(
        amount=Decimal("42.00"),
        currency="EUR",
        description="Abonnement mensuel",
        customer_email="client@example.test",
        success_return_url="https://app.example.test/success",
        cancel_return_url="https://app.example.test/cancel",
        webhook_url="https://app.example.test/webhook",
        metadata={"subscription_id": "sub-1", "requested_billing_method": "SEPA_DEBIT"},
        save_payment_method=True,
    )


def _recurring_payload() -> RecurringChargeRequest:
    return RecurringChargeRequest(
        amount=Decimal("42.00"),
        currency="EUR",
        description="Abonnement mensuel",
        customer_reference="cus_test_123",
        mandate_reference=None,
        idempotency_key="subscription_charge:cycle-1:1",
        payment_method_reference="pm_test_123",
        customer_email="client@example.test",
    )


def test_stripe_initial_subscription_checkout_forces_card_and_saves_it(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request_form(**kwargs: object) -> tuple[int, dict[str, object], str]:
        captured.update(kwargs)
        return 200, {"id": "cs_test_123", "url": "https://checkout.stripe.test/123", "status": "open"}, ""

    monkeypatch.setattr(payment_checkout, "_request_form", fake_request_form)
    result = payment_checkout._stripe_create_checkout("sk_test", _checkout_payload())

    assert result.success is True
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["mode"] == "payment"
    assert body["payment_method_types[0]"] == "card"
    assert body["customer_creation"] == "always"
    assert body["payment_intent_data[setup_future_usage]"] == "off_session"
    assert body["metadata[requested_billing_method]"] == "SEPA_DEBIT"
    assert body["payment_intent_data[metadata][subscription_id]"] == "sub-1"


def test_stripe_sepa_setup_checkout_uses_existing_customer(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(payment_checkout, "resolve_active_secret", lambda *_args, **_kwargs: "sk_test")

    def fake_request_form(**kwargs: object) -> tuple[int, dict[str, object], str]:
        captured.update(kwargs)
        return 200, {"id": "cs_setup_123", "url": "https://checkout.stripe.test/setup", "status": "open"}, ""

    monkeypatch.setattr(payment_checkout, "_request_form", fake_request_form)
    result = payment_checkout.create_stripe_payment_method_setup_session(
        object(),  # type: ignore[arg-type]
        customer_reference="cus_test_123",
        success_return_url="https://app.example.test/success",
        cancel_return_url="https://app.example.test/cancel",
        metadata={"subscription_id": "sub-1"},
    )

    assert result.success is True
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["mode"] == "setup"
    assert body["customer"] == "cus_test_123"
    assert body["payment_method_types[0]"] == "sepa_debit"
    assert body["setup_intent_data[metadata][subscription_id]"] == "sub-1"


def test_stripe_checkout_lookup_extracts_saved_card_and_customer(monkeypatch) -> None:
    monkeypatch.setattr(
        payment_checkout,
        "_request_form",
        lambda **_kwargs: (
            200,
            {
                "id": "cs_test_123",
                "mode": "payment",
                "status": "complete",
                "payment_status": "paid",
                "customer": "cus_test_123",
                "metadata": {"subscription_id": "sub-1"},
                "payment_intent": {
                    "id": "pi_test_123",
                    "payment_method": {
                        "id": "pm_test_123",
                        "type": "card",
                        "card": {"exp_month": 7, "exp_year": 2031},
                    },
                },
            },
            "",
        ),
    )

    result = payment_checkout._stripe_lookup_payment("sk_test", "cs_test_123")

    assert result.paid is True
    assert result.metadata["customer_reference"] == "cus_test_123"
    assert result.payment_method_reference == "pm_test_123"
    assert result.payment_method_type == "card"
    assert result.payment_method_exp_month == 7
    assert result.payment_method_exp_year == 2031


def test_stripe_setup_lookup_extracts_sepa_payment_method_and_mandate(monkeypatch) -> None:
    monkeypatch.setattr(
        payment_checkout,
        "_request_form",
        lambda **_kwargs: (
            200,
            {
                "id": "cs_setup_123",
                "mode": "setup",
                "status": "complete",
                "customer": "cus_test_123",
                "metadata": {"subscription_id": "sub-1"},
                "setup_intent": {
                    "id": "seti_test_123",
                    "mandate": "mandate_test_123",
                    "payment_method": {"id": "pm_sepa_123", "type": "sepa_debit"},
                },
            },
            "",
        ),
    )

    result = payment_checkout._stripe_lookup_payment("sk_test", "cs_setup_123")

    assert result.setup_complete is True
    assert result.paid is False
    assert result.payment_method_reference == "pm_sepa_123"
    assert result.payment_method_type == "sepa_debit"
    assert result.metadata["mandate_reference"] == "mandate_test_123"


def test_stripe_recurring_charge_is_off_session_and_idempotent(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured["timeout"] = timeout
        captured["body"] = parse_qs(request.data.decode("utf-8"))
        captured["headers"] = dict(request.header_items())
        return _Response({"id": "pi_test_renewal", "status": "succeeded"})

    monkeypatch.setattr(psp_gateway, "urlopen", fake_urlopen)
    result = StripeGateway(api_key="sk_test").create_recurring_charge(_recurring_payload())

    assert result.success is True
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["customer"] == ["cus_test_123"]
    assert body["payment_method"] == ["pm_test_123"]
    assert body["confirm"] == ["true"]
    assert body["off_session"] == ["true"]
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Idempotency-key"] == "subscription_charge:cycle-1:1"


def test_stripe_sepa_processing_is_pending(monkeypatch) -> None:
    monkeypatch.setattr(
        psp_gateway,
        "urlopen",
        lambda *_args, **_kwargs: _Response({"id": "pi_test_processing", "status": "processing"}),
    )

    result = StripeGateway(api_key="sk_test").create_recurring_charge(_recurring_payload())

    assert result.success is False
    assert result.pending is True
    assert result.status == "PROCESSING"
    assert result.provider_reference == "pi_test_processing"


def test_stripe_reference_detection() -> None:
    assert detect_provider_from_reference("cs_test_123") == PaymentProvider.STRIPE
    assert detect_provider_from_reference("pi_test_123") == PaymentProvider.STRIPE
    assert detect_provider_from_reference("seti_test_123") == PaymentProvider.STRIPE


def test_stripe_webhook_extracts_nested_object_not_event_id() -> None:
    request = SimpleNamespace(query_params={})

    reference = _extract_reference(
        request,  # type: ignore[arg-type]
        {
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_123"}},
        },
    )

    assert reference == "cs_test_123"


def test_stripe_webhook_signature_is_verified_with_tolerance() -> None:
    raw_body = b'{"id":"evt_test_123"}'
    timestamp = 1_800_000_000
    secret = "whsec_test_123"
    signature = hmac.new(
        secret.encode("utf-8"),
        str(timestamp).encode("ascii") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()

    assert _verify_stripe_webhook_signature(
        raw_body,
        f"t={timestamp},v1={signature}",
        secret,
        now_timestamp=timestamp + 30,
    ) is True
    assert _verify_stripe_webhook_signature(
        raw_body,
        f"t={timestamp},v1={signature}",
        secret,
        now_timestamp=timestamp + 301,
    ) is False
