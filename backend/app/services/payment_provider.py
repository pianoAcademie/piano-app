from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ops import AppSetting, LegalEntity


class PaymentProvider(str, Enum):
    PAYPLUG = "PAYPLUG"
    MOLLIE = "MOLLIE"
    STRIPE = "STRIPE"


class PaymentMode(str, Enum):
    TEST = "TEST"
    LIVE = "LIVE"


PAYMENT_PROVIDER_SETTING_KEY = "config_payment_provider"
PAYMENT_MODE_SETTING_KEY = "config_payment_mode"
PAYPLUG_TEST_SECRET_SETTING_KEY = "config_payplug_test_secret"
PAYPLUG_LIVE_SECRET_SETTING_KEY = "config_payplug_live_secret"
MOLLIE_TEST_API_KEY_SETTING_KEY = "config_mollie_test_api_key"
MOLLIE_LIVE_API_KEY_SETTING_KEY = "config_mollie_live_api_key"
STRIPE_TEST_SECRET_SETTING_KEY = "config_stripe_test_secret"
STRIPE_LIVE_SECRET_SETTING_KEY = "config_stripe_live_secret"
PAYMENT_WEBHOOK_SECRET_SETTING_KEY = "config_payment_webhook_secret"


@dataclass(frozen=True)
class PaymentProviderCapabilities:
    subscriptions_supported: bool
    subscriptions_managed_by_psp: bool
    recommendation: str


CAPABILITIES_BY_PROVIDER: dict[PaymentProvider, PaymentProviderCapabilities] = {
    PaymentProvider.PAYPLUG: PaymentProviderCapabilities(
        subscriptions_supported=True,
        subscriptions_managed_by_psp=False,
        recommendation="Payplug accepte le paiement recurrent via carte enregistree, mais l'echeancier est gere par l'application.",
    ),
    PaymentProvider.MOLLIE: PaymentProviderCapabilities(
        subscriptions_supported=True,
        subscriptions_managed_by_psp=True,
        recommendation="Mollie fournit une API Subscription native (mandats, retries, cycle recurrent gere par le PSP).",
    ),
    PaymentProvider.STRIPE: PaymentProviderCapabilities(
        subscriptions_supported=False,
        subscriptions_managed_by_psp=True,
        recommendation="Stripe est disponible pour les paiements one-shot checkout. Le recurrent n'est pas encore active dans ce module.",
    ),
}


def _get_setting(db: Session, key: str) -> AppSetting | None:
    return db.query(AppSetting).filter(AppSetting.key == key).one_or_none()


def get_setting_value(db: Session, key: str) -> str | None:
    setting = _get_setting(db, key)
    if setting is None:
        return None
    return setting.value


def set_setting_value(db: Session, key: str, value: str | None) -> None:
    setting = _get_setting(db, key)
    normalized = (value or "").strip()
    now = datetime.now(timezone.utc)
    if setting is None:
        db.add(AppSetting(key=key, value=normalized, updated_at=now))
        return
    setting.value = normalized
    setting.updated_at = now
    db.add(setting)


def parse_provider(raw: str | None) -> PaymentProvider:
    normalized = (raw or "").strip().upper()
    if normalized == PaymentProvider.STRIPE.value:
        return PaymentProvider.STRIPE
    if normalized == PaymentProvider.MOLLIE.value:
        return PaymentProvider.MOLLIE
    return PaymentProvider.PAYPLUG


def detect_provider_from_reference(payment_reference: str | None) -> PaymentProvider | None:
    normalized = (payment_reference or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("cs_"):
        return PaymentProvider.STRIPE
    if normalized.startswith("tr_"):
        return PaymentProvider.MOLLIE
    return None


def parse_mode(raw: str | None) -> PaymentMode:
    normalized = (raw or "").strip().upper()
    if normalized == PaymentMode.LIVE.value:
        return PaymentMode.LIVE
    return PaymentMode.TEST


def mask_secret(value: str | None) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}...{token[-4:]}"


def _db_or_env(db_value: str | None, env_value: str) -> str:
    if db_value and db_value.strip():
        return db_value.strip()
    return env_value.strip()


def resolve_provider(db: Session, *, legal_entity_id: UUID | None = None) -> PaymentProvider:
    if legal_entity_id is not None:
        entity_provider = db.scalar(select(LegalEntity.default_payment_provider).where(LegalEntity.id == legal_entity_id))
        if entity_provider and str(entity_provider).strip():
            return parse_provider(str(entity_provider))
    return parse_provider(get_setting_value(db, PAYMENT_PROVIDER_SETTING_KEY) or settings.payment_provider_default)


def resolve_mode(db: Session) -> PaymentMode:
    return parse_mode(get_setting_value(db, PAYMENT_MODE_SETTING_KEY) or settings.payment_mode_default)


def resolve_secret_values(db: Session) -> dict[str, str]:
    payplug_test_secret = _db_or_env(get_setting_value(db, PAYPLUG_TEST_SECRET_SETTING_KEY), settings.payplug_test_secret_key)
    payplug_live_secret = _db_or_env(get_setting_value(db, PAYPLUG_LIVE_SECRET_SETTING_KEY), settings.payplug_live_secret_key)
    mollie_test_api_key = _db_or_env(get_setting_value(db, MOLLIE_TEST_API_KEY_SETTING_KEY), settings.mollie_test_api_key)
    mollie_live_api_key = _db_or_env(get_setting_value(db, MOLLIE_LIVE_API_KEY_SETTING_KEY), settings.mollie_live_api_key)
    stripe_test_secret = _db_or_env(get_setting_value(db, STRIPE_TEST_SECRET_SETTING_KEY), settings.stripe_test_secret_key)
    stripe_live_secret = _db_or_env(get_setting_value(db, STRIPE_LIVE_SECRET_SETTING_KEY), settings.stripe_live_secret_key)
    webhook_secret = _db_or_env(get_setting_value(db, PAYMENT_WEBHOOK_SECRET_SETTING_KEY), settings.payment_webhook_secret)
    return {
        "payplug_test_secret": payplug_test_secret,
        "payplug_live_secret": payplug_live_secret,
        "mollie_test_api_key": mollie_test_api_key,
        "mollie_live_api_key": mollie_live_api_key,
        "stripe_test_secret": stripe_test_secret,
        "stripe_live_secret": stripe_live_secret,
        "webhook_secret": webhook_secret,
    }


def resolve_webhook_secret(db: Session | None = None) -> str:
    if db is not None:
        explicit = resolve_secret_values(db)["webhook_secret"].strip()
        if explicit:
            return explicit
    elif settings.payment_webhook_secret.strip():
        return settings.payment_webhook_secret.strip()

    seed = f"{settings.jwt_secret_key}|payment-webhook|{settings.frontend_base_url}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


def resolve_active_secret(db: Session, *, provider: PaymentProvider | None = None) -> str:
    selected_provider = provider or resolve_provider(db)
    mode = resolve_mode(db)
    values = resolve_secret_values(db)
    if selected_provider == PaymentProvider.PAYPLUG:
        return values["payplug_live_secret"] if mode == PaymentMode.LIVE else values["payplug_test_secret"]
    if selected_provider == PaymentProvider.MOLLIE:
        return values["mollie_live_api_key"] if mode == PaymentMode.LIVE else values["mollie_test_api_key"]
    return values["stripe_live_secret"] if mode == PaymentMode.LIVE else values["stripe_test_secret"]
