from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services import payment_checkout, psp_gateway
from app.services.payment_checkout import CheckoutCreateRequest
from app.services.payment_provider import PaymentProvider, detect_provider_from_reference
from app.services.psp_gateway import PayplugGateway, RecurringChargeRequest
from app.services.subscription_billing import _record_attempt


class _Response:
    def __init__(self, payload: dict[str, object], *, status: int = 201) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _recurring_payload(**overrides: object) -> RecurringChargeRequest:
    values: dict[str, object] = {
        "amount": Decimal("42.00"),
        "currency": "EUR",
        "description": "Abonnement mensuel",
        "customer_reference": None,
        "mandate_reference": None,
        "idempotency_key": "subscription_charge:cycle-1:1",
        "payment_method_reference": "card_test_123",
        "payment_method_exp_month": 12,
        "payment_method_exp_year": 2099,
        "customer_email": "client@example.test",
        "customer_first_name": "Ada",
        "customer_last_name": "Lovelace",
        "success_return_url": "https://app.example.test/success",
        "cancel_return_url": "https://app.example.test/cancel",
        "notification_url": "https://app.example.test/webhook?token=signed",
    }
    values.update(overrides)
    return RecurringChargeRequest(**values)  # type: ignore[arg-type]


def test_payplug_checkout_requests_card_saving(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request_json(**kwargs: object) -> tuple[int, dict[str, object], str]:
        captured.update(kwargs)
        return 201, {
            "id": "pay_checkout_1",
            "hosted_payment": {"payment_url": "https://secure.payplug.test/checkout"},
        }, ""

    monkeypatch.setattr(payment_checkout, "_request_json", fake_request_json)
    result = payment_checkout._payplug_create_checkout(
        "sk_test",
        CheckoutCreateRequest(
            amount=Decimal("42.00"),
            currency="EUR",
            description="Abonnement",
            customer_email="client@example.test",
            customer_first_name="Ada",
            customer_last_name="Lovelace",
            customer_country="FR",
            success_return_url="https://app.example.test/success",
            cancel_return_url="https://app.example.test/cancel",
            webhook_url="https://app.example.test/webhook",
            metadata={"subscription_id": "sub-1"},
            save_payment_method=True,
        ),
    )

    assert result.success is True
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["save_card"] is True
    assert body["customer"] == {
        "email": "client@example.test",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "country": "FR",
    }


def test_payplug_lookup_extracts_card_only_from_trusted_api_response(monkeypatch) -> None:
    monkeypatch.setattr(
        payment_checkout,
        "_request_json",
        lambda **_kwargs: (
            200,
            {
                "id": "pay_123",
                "is_paid": True,
                "metadata": {"subscription_id": "sub-1"},
                "card": {"id": "card_secure_123", "exp_month": 7, "exp_year": 2031},
            },
            "",
        ),
    )

    result = payment_checkout._payplug_lookup_payment("sk_test", "pay_123")

    assert result.paid is True
    assert result.payment_method_reference == "card_secure_123"
    assert result.payment_method_exp_month == 7
    assert result.payment_method_exp_year == 2031


def test_payplug_recurring_charge_uses_merchant_initiator_and_idempotency(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["headers"] = dict(request.header_items())
        return _Response({"id": "pay_recurring_1", "is_paid": True})

    monkeypatch.setattr(psp_gateway, "urlopen", fake_urlopen)
    result = PayplugGateway(api_key="sk_test").create_recurring_charge(_recurring_payload())

    assert result.success is True
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["payment_method"] == "card_test_123"
    assert body["initiator"] == "MERCHANT"
    assert body["metadata"] == {
        "source": "SUBSCRIPTION_RENEWAL",
        "idempotency_key": "subscription_charge:cycle-1:1",
    }


def test_payplug_expired_card_fails_without_calling_api(monkeypatch) -> None:
    def should_not_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Payplug API must not be called for an expired saved card")

    monkeypatch.setattr(psp_gateway, "urlopen", should_not_call)
    result = PayplugGateway(api_key="sk_test").create_recurring_charge(
        _recurring_payload(
            payment_method_exp_month=1,
            payment_method_exp_year=2020,
        )
    )

    assert result.success is False
    assert result.status == "CARD_EXPIRED"
    assert result.retryable is False


def test_payplug_provider_failure_is_normalized(monkeypatch) -> None:
    monkeypatch.setattr(
        psp_gateway,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {"id": "pay_failed_1", "failure": {"code": "card_declined", "message": "Declined"}}
        ),
    )

    result = PayplugGateway(api_key="sk_test").create_recurring_charge(_recurring_payload())

    assert result.success is False
    assert result.status == "CARD_DECLINED"
    assert result.retryable is False


def test_payplug_new_authentication_returns_recovery_url(monkeypatch) -> None:
    monkeypatch.setattr(
        psp_gateway,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            {
                "id": "pay_auth_1",
                "is_paid": False,
                "hosted_payment": {"payment_url": "https://secure.payplug.test/3ds"},
            }
        ),
    )

    result = PayplugGateway(api_key="sk_test").create_recurring_charge(_recurring_payload())

    assert result.success is False
    assert result.status == "AUTHENTICATION_REQUIRED"
    assert result.provider_reference == "pay_auth_1"
    assert result.checkout_url == "https://secure.payplug.test/3ds"


def test_payplug_reference_detection() -> None:
    assert detect_provider_from_reference("pay_123") == PaymentProvider.PAYPLUG


def test_subscription_attempt_idempotency_skips_existing_key() -> None:
    existing_attempt = object()

    class _Db:
        def scalar(self, _query: object) -> object:
            return existing_attempt

        def add(self, _value: object) -> None:
            raise AssertionError("A duplicate payment attempt must not be inserted")

    result = _record_attempt(
        _Db(),  # type: ignore[arg-type]
        cycle=SimpleNamespace(),
        attempt_number=1,
        attempted_at=datetime.now(timezone.utc),
        idempotency_key="subscription_charge:cycle-1:1",
    )

    assert result is None


def test_expiration_boundary_keeps_current_month_valid() -> None:
    now = datetime(2030, 7, 16, tzinfo=timezone.utc)
    assert PayplugGateway._card_is_expired(7, 2030, now=now) is False
    assert PayplugGateway._card_is_expired(6, 2030, now=now) is True
