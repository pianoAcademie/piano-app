from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import logging
import re
import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client_record import ClientManualTransaction, ClientNoteEntry
from app.models.family import ClientFamilyLink
from app.models.ops import AppSetting
from app.models.quote import Quote
from app.models.referral import ReferralReward
from app.models.typeform_intake import TypeformIntake
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_sender_profile

logger = logging.getLogger(__name__)

REFERRAL_PROGRAM_SETTING_KEY = "config_referral_program_v1"

REFERRAL_STATUS_DECLARED = "DECLARED"
REFERRAL_STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
REFERRAL_STATUS_AWAITING_PAYMENT = "AWAITING_PAYMENT"
REFERRAL_STATUS_CREDIT_GRANTED = "CREDIT_GRANTED"
REFERRAL_STATUS_CANCELLED = "CANCELLED"

REFERRAL_MATCH_UNMATCHED = "UNMATCHED"
REFERRAL_MATCH_AMBIGUOUS = "AMBIGUOUS"
REFERRAL_MATCH_AUTO = "AUTO_MATCHED"
REFERRAL_MATCH_MANUAL = "MANUAL_MATCHED"

REFERRAL_CATEGORIES = ("PARIS", "BAR_LE_DUC", "ONLINE", "DOMICILE")
REFERRAL_PAID_STATUSES = {"PAID", "COMPLETED", "SUCCEEDED"}


DEFAULT_REFERRAL_PROGRAM_CONFIG: dict[str, object] = {
    "enabled": True,
    "currency": "EUR",
    "trigger_ratio": "0.50",
    "announcement_email_enabled": True,
    "credit_email_enabled": True,
    "categories": {
        "PARIS": {"label": "Paris", "amount": "50.00", "active": True},
        "BAR_LE_DUC": {"label": "Bar-le-Duc", "amount": "50.00", "active": True},
        "ONLINE": {"label": "En ligne", "amount": "50.00", "active": True},
        "DOMICILE": {"label": "Domicile", "amount": "50.00", "active": True},
    },
}


@dataclass(frozen=True)
class ReferralProgramConfig:
    enabled: bool
    currency: str
    trigger_ratio: Decimal
    announcement_email_enabled: bool
    credit_email_enabled: bool
    category_amounts: dict[str, Decimal]
    category_labels: dict[str, str]
    category_active: dict[str, bool]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_referral_text(value: object | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9@+]+", " ", ascii_text.casefold()).strip()


def _display_name(user: User | None) -> str:
    if user is None:
        return ""
    return " ".join(part for part in [user.first_name, user.last_name] if part).strip() or user.email or str(user.id)


def _decimal(value: object, fallback: Decimal) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def _ratio_decimal(value: object, fallback: Decimal) -> Decimal:
    try:
        ratio = Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, TypeError, ValueError):
        return fallback
    if ratio <= Decimal("0") or ratio > Decimal("1"):
        return fallback
    return ratio


def referral_program_config(db: Session) -> ReferralProgramConfig:
    raw = dict(DEFAULT_REFERRAL_PROGRAM_CONFIG)
    row = db.scalar(select(AppSetting).where(AppSetting.key == REFERRAL_PROGRAM_SETTING_KEY))
    if row is not None and (row.value or "").strip():
        try:
            parsed = json.loads(row.value)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            raw.update(parsed)
            raw_categories = raw.get("categories")
            parsed_categories = parsed.get("categories")
            if isinstance(raw_categories, dict) and isinstance(parsed_categories, dict):
                merged_categories = dict(DEFAULT_REFERRAL_PROGRAM_CONFIG["categories"])  # type: ignore[index]
                merged_categories.update(parsed_categories)
                raw["categories"] = merged_categories

    currency = str(raw.get("currency") or "EUR").strip().upper()[:3] or "EUR"
    categories = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
    category_amounts: dict[str, Decimal] = {}
    category_labels: dict[str, str] = {}
    category_active: dict[str, bool] = {}
    for code in REFERRAL_CATEGORIES:
        item = categories.get(code) if isinstance(categories, dict) else None
        item = item if isinstance(item, dict) else {}
        category_amounts[code] = _decimal(item.get("amount"), Decimal("50.00"))
        category_labels[code] = str(item.get("label") or code).strip() or code
        category_active[code] = bool(item.get("active", True))

    return ReferralProgramConfig(
        enabled=bool(raw.get("enabled", True)),
        currency=currency,
        trigger_ratio=_ratio_decimal(raw.get("trigger_ratio"), Decimal("0.5000")),
        announcement_email_enabled=bool(raw.get("announcement_email_enabled", True)),
        credit_email_enabled=bool(raw.get("credit_email_enabled", True)),
        category_amounts=category_amounts,
        category_labels=category_labels,
        category_active=category_active,
    )


def referral_category_for_location(value: object | None) -> str | None:
    token = normalize_referral_text(value)
    if not token:
        return None
    if "domicile" in token:
        return "DOMICILE"
    if "video" in token or "visio" in token or "online" in token or "ligne" in token or "call" in token:
        return "ONLINE"
    if "bar le duc" in token or "barleduc" in token or "bar" in token and "duc" in token:
        return "BAR_LE_DUC"
    if any(site in token for site in ("richelieu", "assas", "pompe", "scheffer")):
        return "PARIS"
    if "paris" in token:
        return "PARIS"
    return None


def referral_reward_amount(db: Session, *, category: str | None) -> tuple[Decimal, str, Decimal]:
    config = referral_program_config(db)
    normalized_category = (category or "").strip().upper()
    if normalized_category not in config.category_amounts:
        normalized_category = "PARIS"
    amount = config.category_amounts.get(normalized_category, Decimal("50.00"))
    if not config.category_active.get(normalized_category, True):
        amount = Decimal("0.00")
    return amount, config.currency, config.trigger_ratio


def _candidate_score(user: User, query: str) -> tuple[int, list[str]]:
    haystack_values = [
        user.first_name,
        user.last_name,
        user.email,
        user.phone,
        user.mobile_phone_1,
        user.mobile_phone_2,
        user.home_phone,
    ]
    haystack = normalize_referral_text(" ".join(str(value or "") for value in haystack_values))
    if not query or not haystack:
        return 0, []
    query_tokens = [token for token in query.split() if len(token) >= 2]
    reasons: list[str] = []
    score = 0
    email_token = normalize_referral_text(user.email)
    if "@" in query and email_token and email_token == query:
        return 100, ["email exact"]
    last_name = normalize_referral_text(user.last_name)
    first_name = normalize_referral_text(user.first_name)
    if last_name and last_name == query:
        score += 85
        reasons.append("nom exact")
    elif last_name and last_name in query_tokens:
        score += 55
        reasons.append("nom present")
    if first_name and first_name in query_tokens:
        score += 20
        reasons.append("prenom present")
    matched_tokens = [token for token in query_tokens if token in haystack]
    if matched_tokens:
        score += min(30, 10 * len(set(matched_tokens)))
        reasons.append("mots retrouves")
    return min(score, 100), reasons


def match_referrer_candidates(
    db: Session,
    *,
    declared_text: str,
    excluded_user_ids: set[UUID] | None = None,
) -> list[dict[str, object]]:
    query = normalize_referral_text(declared_text)
    if not query:
        return []
    excluded = excluded_user_ids or set()
    users = db.scalars(
        select(User)
        .where(
            User.role == UserRole.CLIENT,
            User.client_kind == ClientKind.ADULT,
            User.client_status.in_([ClientStatus.ACTIVE, ClientStatus.RESPONSABLE, ClientStatus.TRIAL, ClientStatus.PENDING]),
            User.is_active.is_(True),
        )
        .order_by(User.last_name.asc().nulls_last(), User.first_name.asc().nulls_last())
        .limit(1000)
    ).all()
    candidates: list[dict[str, object]] = []
    for user in users:
        if user.id in excluded:
            continue
        score, reasons = _candidate_score(user, query)
        if score < 35:
            continue
        candidates.append(
            {
                "user_id": str(user.id),
                "display_name": _display_name(user),
                "email": user.email,
                "confidence": score,
                "reasons": reasons,
            }
        )
    candidates.sort(key=lambda item: int(item.get("confidence") or 0), reverse=True)
    return candidates[:8]


def _match_status_for_candidates(candidates: list[dict[str, object]]) -> tuple[str, UUID | None, int]:
    if not candidates:
        return REFERRAL_MATCH_UNMATCHED, None, 0
    top = candidates[0]
    top_score = int(top.get("confidence") or 0)
    if top_score >= 85 and (len(candidates) == 1 or top_score - int(candidates[1].get("confidence") or 0) >= 20):
        try:
            return REFERRAL_MATCH_AUTO, UUID(str(top.get("user_id"))), top_score
        except (ValueError, TypeError):
            return REFERRAL_MATCH_AMBIGUOUS, None, top_score
    return REFERRAL_MATCH_AMBIGUOUS, None, top_score


def _linked_child_ids_for_adult(db: Session, user_id: UUID | None) -> set[UUID]:
    if user_id is None:
        return set()
    rows = db.scalars(select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id == user_id)).all()
    out: set[UUID] = set()
    for row in rows:
        try:
            out.add(row if isinstance(row, UUID) else UUID(str(row)))
        except (TypeError, ValueError):
            continue
    return out


def _identity_token(value: object | None) -> str:
    return normalize_referral_text(value).replace(" ", "")


def _phone_token(value: object | None) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _intake_family_identity(normalized: dict[str, object]) -> dict[str, str]:
    identity = {
        "parent_first_name": str(normalized.get("parent_first_name") or "").strip(),
        "parent_last_name": str(normalized.get("parent_last_name") or "").strip(),
        "parent_email": str(normalized.get("parent_email") or "").strip().lower(),
        "parent_phone": str(normalized.get("parent_phone") or "").strip(),
        "child_first_name": str(normalized.get("child_first_name") or "").strip(),
        "child_last_name": str(normalized.get("child_last_name") or "").strip(),
    }
    return {key: value for key, value in identity.items() if value}


def _user_matches_person_identity(user: User | None, *, first_name: str, last_name: str, email: str = "", phone: str = "") -> bool:
    if user is None:
        return False
    if email and normalize_referral_text(user.email) == normalize_referral_text(email):
        return True
    if phone:
        user_phones = [user.phone, user.mobile_phone_1, user.mobile_phone_2, user.home_phone]
        expected_phone = _phone_token(phone)
        if expected_phone and any(_phone_token(value) == expected_phone for value in user_phones):
            return True
    expected_first = _identity_token(first_name)
    expected_last = _identity_token(last_name)
    if expected_first and expected_last:
        return _identity_token(user.first_name) == expected_first and _identity_token(user.last_name) == expected_last
    return False


def _referrer_matches_intake_family(db: Session, *, referrer_user_id: UUID | None, normalized: dict[str, object]) -> bool:
    if referrer_user_id is None:
        return False
    identity = _intake_family_identity(normalized)
    if not identity:
        return False
    referrer = db.scalar(select(User).where(User.id == referrer_user_id))
    if _user_matches_person_identity(
        referrer,
        first_name=identity.get("parent_first_name", ""),
        last_name=identity.get("parent_last_name", ""),
        email=identity.get("parent_email", ""),
        phone=identity.get("parent_phone", ""),
    ):
        return True

    child_first_name = identity.get("child_first_name", "")
    child_last_name = identity.get("child_last_name", "")
    if not child_first_name or not child_last_name:
        return False
    child_ids = _linked_child_ids_for_adult(db, referrer_user_id)
    if not child_ids:
        return False
    children = db.scalars(select(User).where(User.id.in_(list(child_ids)))).all()
    return any(
        _user_matches_person_identity(child, first_name=child_first_name, last_name=child_last_name)
        for child in children
    )


def _filter_intake_self_referral_candidates(
    db: Session,
    *,
    candidates: list[dict[str, object]],
    normalized: dict[str, object],
) -> tuple[list[dict[str, object]], bool]:
    filtered: list[dict[str, object]] = []
    blocked = False
    for candidate in candidates:
        raw_user_id = candidate.get("user_id") if isinstance(candidate, dict) else None
        try:
            candidate_user_id = UUID(str(raw_user_id))
        except (TypeError, ValueError):
            continue
        if _referrer_matches_intake_family(db, referrer_user_id=candidate_user_id, normalized=normalized):
            blocked = True
            continue
        filtered.append(candidate)
    return filtered, blocked


def _reward_intake_family_identity(db: Session, reward: ReferralReward) -> dict[str, str]:
    metadata = reward.metadata_json or {}
    raw_identity = metadata.get("referred_family_identity")
    if isinstance(raw_identity, dict):
        identity = {str(key): str(value).strip() for key, value in raw_identity.items() if str(value or "").strip()}
        if identity:
            return identity
    if not hasattr(db, "scalar"):
        return {}
    typeform_intake_id = getattr(reward, "typeform_intake_id", None)
    if typeform_intake_id is not None:
        intake = db.scalar(select(TypeformIntake).where(TypeformIntake.id == typeform_intake_id))
        if intake is not None:
            identity = _intake_family_identity(intake.normalized_payload_json or {})
            if identity:
                return identity
    quote_id = getattr(reward, "quote_id", None)
    if quote_id is not None:
        quote = db.scalar(select(Quote).where(Quote.id == quote_id))
        if quote is not None:
            quote_meta = quote.meta or {}
            typeform_meta = quote_meta.get("typeform_intake") if isinstance(quote_meta, dict) else None
            normalized = typeform_meta.get("normalized_payload") if isinstance(typeform_meta, dict) else None
            if isinstance(normalized, dict):
                return _intake_family_identity(normalized)
    return {}


def _referrer_matches_reward_intake_family(
    db: Session,
    *,
    referrer_user_id: UUID | None,
    reward: ReferralReward,
) -> bool:
    if referrer_user_id is None:
        return False
    identity = _reward_intake_family_identity(db, reward)
    if not identity:
        return False
    return _referrer_matches_intake_family(db, referrer_user_id=referrer_user_id, normalized=identity)


def refresh_referral_self_family_guard(db: Session, reward: ReferralReward) -> bool:
    if reward.status == REFERRAL_STATUS_CREDIT_GRANTED or reward.referrer_user_id is None:
        return False
    if is_same_referral_family(
        db,
        referrer_user_id=reward.referrer_user_id,
        referred_client_id=reward.referred_client_id,
        referred_student_id=reward.referred_student_id,
    ) or _referrer_matches_reward_intake_family(db, referrer_user_id=reward.referrer_user_id, reward=reward):
        _block_self_referral(reward)
        reward.updated_at = utcnow()
        db.add(reward)
        return True
    return False


def is_same_referral_family(
    db: Session,
    *,
    referrer_user_id: UUID | None,
    referred_client_id: UUID | None,
    referred_student_id: UUID | None,
) -> bool:
    if referrer_user_id is None:
        return False
    referred_ids = {user_id for user_id in (referred_client_id, referred_student_id) if user_id is not None}
    if referrer_user_id in referred_ids:
        return True

    referrer_child_ids = _linked_child_ids_for_adult(db, referrer_user_id)
    if referrer_child_ids.intersection(referred_ids):
        return True

    referred_family_child_ids: set[UUID] = set()
    for user_id in referred_ids:
        referred_family_child_ids.update(_linked_child_ids_for_adult(db, user_id))
    return bool(referrer_child_ids and referrer_child_ids.intersection(referred_family_child_ids))


def _block_self_referral(reward: ReferralReward) -> None:
    reward.status = REFERRAL_STATUS_CANCELLED
    reward.match_status = REFERRAL_MATCH_UNMATCHED
    reward.referrer_user_id = None
    reward.match_confidence = 0
    reward.metadata_json = {**(reward.metadata_json or {}), "self_referral_blocked": True}


def referral_match_candidates_for_reward(db: Session, reward: ReferralReward) -> list[dict[str, object]]:
    candidates = reward.match_candidates_json or []
    filtered: list[dict[str, object]] = []
    for candidate in candidates:
        raw_user_id = candidate.get("user_id") if isinstance(candidate, dict) else None
        try:
            candidate_user_id = UUID(str(raw_user_id))
        except (TypeError, ValueError):
            continue
        if is_same_referral_family(
            db,
            referrer_user_id=candidate_user_id,
            referred_client_id=reward.referred_client_id,
            referred_student_id=reward.referred_student_id,
        ):
            continue
        filtered.append(candidate)
    return filtered


def ensure_referral_for_intake(
    db: Session,
    *,
    intake: TypeformIntake,
    normalized: dict[str, object],
) -> ReferralReward | None:
    declared_text = str(normalized.get("referral_referrer_name") or "").strip()
    if not declared_text:
        reward = db.scalar(select(ReferralReward).where(ReferralReward.typeform_intake_id == intake.id).with_for_update())
        if reward is not None and reward.status != REFERRAL_STATUS_CREDIT_GRANTED:
            reward.status = REFERRAL_STATUS_CANCELLED
            reward.updated_at = utcnow()
            db.add(reward)
            return reward
        return None
    config = referral_program_config(db)
    if not config.enabled:
        return None
    category = str(normalized.get("referral_category") or "").strip().upper() or referral_category_for_location(
        normalized.get("requested_location")
    )
    amount, currency, trigger_ratio = referral_reward_amount(db, category=category)
    candidates = match_referrer_candidates(db, declared_text=declared_text)
    candidates, intake_self_referral_blocked = _filter_intake_self_referral_candidates(
        db,
        candidates=candidates,
        normalized=normalized,
    )
    match_status, referrer_id, confidence = _match_status_for_candidates(candidates)
    reward_status = REFERRAL_STATUS_AWAITING_PAYMENT if referrer_id is not None else REFERRAL_STATUS_NEEDS_REVIEW
    if intake_self_referral_blocked and referrer_id is None:
        match_status = REFERRAL_MATCH_UNMATCHED
        confidence = 0
        reward_status = REFERRAL_STATUS_CANCELLED
    now = utcnow()
    metadata = {
        "source": "typeform",
        "referred_family_identity": _intake_family_identity(normalized),
    }
    if intake_self_referral_blocked:
        metadata["self_referral_blocked"] = True
    reward = db.scalar(select(ReferralReward).where(ReferralReward.typeform_intake_id == intake.id).with_for_update())
    if reward is None:
        reward = ReferralReward(
            typeform_intake_id=intake.id,
            declared_referrer_text=declared_text,
            category=category,
            status=reward_status,
            match_status=match_status,
            referrer_user_id=referrer_id,
            match_confidence=confidence,
            match_candidates_json=candidates,
            reward_amount=amount,
            currency=currency,
            trigger_ratio=trigger_ratio,
            validated_at=now if referrer_id is not None else None,
            metadata_json=metadata,
            created_at=now,
            updated_at=now,
        )
    elif reward.status != REFERRAL_STATUS_CREDIT_GRANTED:
        reward.declared_referrer_text = declared_text
        reward.category = category
        reward.reward_amount = amount
        reward.currency = currency
        reward.trigger_ratio = trigger_ratio
        reward.match_candidates_json = candidates
        reward.match_confidence = confidence
        if reward.match_status != REFERRAL_MATCH_MANUAL:
            reward.match_status = match_status
            reward.referrer_user_id = referrer_id
            reward.status = reward_status
            reward.validated_at = now if referrer_id is not None else None
        reward.metadata_json = {**(reward.metadata_json or {}), **metadata}
        reward.updated_at = now
    db.add(reward)
    return reward


def link_referral_to_quote(db: Session, *, intake_id: UUID, quote_id: UUID) -> ReferralReward | None:
    reward = db.scalar(select(ReferralReward).where(ReferralReward.typeform_intake_id == intake_id).with_for_update())
    if reward is None:
        return None
    reward.quote_id = quote_id
    reward.updated_at = utcnow()
    db.add(reward)
    return reward


def ensure_referral_for_sibling_quote(
    db: Session,
    *,
    source_quote_id: UUID,
    sibling_quote_id: UUID,
    sibling_prospect_id: UUID | None = None,
) -> ReferralReward | None:
    existing = db.scalar(select(ReferralReward).where(ReferralReward.quote_id == sibling_quote_id).with_for_update())
    if existing is not None:
        return existing
    source = db.scalar(select(ReferralReward).where(ReferralReward.quote_id == source_quote_id))
    if source is None:
        return None
    now = utcnow()
    reward = ReferralReward(
        typeform_intake_id=None,
        quote_id=sibling_quote_id,
        declared_referrer_text=source.declared_referrer_text,
        category=source.category,
        status=REFERRAL_STATUS_AWAITING_PAYMENT if source.referrer_user_id is not None else REFERRAL_STATUS_NEEDS_REVIEW,
        match_status=source.match_status,
        referrer_user_id=source.referrer_user_id,
        match_confidence=source.match_confidence,
        match_candidates_json=source.match_candidates_json or [],
        reward_amount=source.reward_amount,
        currency=source.currency,
        trigger_ratio=source.trigger_ratio,
        validated_at=now if source.referrer_user_id is not None else None,
        metadata_json={
            "source": "quote_sibling",
            "source_reward_id": str(source.id),
            "source_quote_id": str(source_quote_id),
            "sibling_prospect_id": str(sibling_prospect_id) if sibling_prospect_id else None,
        },
        created_at=now,
        updated_at=now,
    )
    db.add(reward)
    return reward


def ensure_referrals_for_sibling_quotes(db: Session) -> int:
    sibling_quotes = db.scalars(select(Quote).where(Quote.parent_quote_id.is_not(None))).all()
    created = 0
    for quote in sibling_quotes:
        quote_meta = quote.meta or {}
        if not quote_meta.get("duplicated_for_child_prospect_id"):
            continue
        before = db.scalar(select(ReferralReward.id).where(ReferralReward.quote_id == quote.id).limit(1))
        if before is not None or quote.parent_quote_id is None:
            continue
        sibling_prospect_id = quote.prospect_id
        raw_sibling_prospect_id = quote_meta.get("duplicated_for_child_prospect_id")
        if raw_sibling_prospect_id:
            try:
                sibling_prospect_id = UUID(str(raw_sibling_prospect_id))
            except (TypeError, ValueError):
                pass
        reward = ensure_referral_for_sibling_quote(
            db,
            source_quote_id=quote.parent_quote_id,
            sibling_quote_id=quote.id,
            sibling_prospect_id=sibling_prospect_id,
        )
        if reward is not None:
            created += 1
    return created


def bind_referral_after_quote_transformation(
    db: Session,
    *,
    quote_id: UUID,
    referred_client_id: UUID,
    referred_student_id: UUID | None,
) -> ReferralReward | None:
    reward = db.scalar(select(ReferralReward).where(ReferralReward.quote_id == quote_id).with_for_update())
    if reward is None:
        return None
    reward.referred_client_id = referred_client_id
    reward.referred_student_id = referred_student_id
    if is_same_referral_family(
        db,
        referrer_user_id=reward.referrer_user_id,
        referred_client_id=referred_client_id,
        referred_student_id=referred_student_id,
    ):
        _block_self_referral(reward)
    elif reward.referrer_user_id is not None and reward.status in {REFERRAL_STATUS_DECLARED, REFERRAL_STATUS_NEEDS_REVIEW}:
        reward.status = REFERRAL_STATUS_AWAITING_PAYMENT
        if reward.validated_at is None:
            reward.validated_at = utcnow()
    reward.updated_at = utcnow()
    db.add(reward)
    if reward.status == REFERRAL_STATUS_AWAITING_PAYMENT:
        try:
            send_referral_announcement_email(db, reward=reward)
        except Exception:
            logger.exception("Unable to send referral announcement email for reward=%s", reward.id)
    return reward


def manually_validate_referral(
    db: Session,
    *,
    reward_id: UUID,
    referrer_user_id: UUID,
    actor_user_id: UUID | None = None,
) -> ReferralReward:
    reward = db.scalar(select(ReferralReward).where(ReferralReward.id == reward_id).with_for_update())
    if reward is None:
        raise ValueError("Referral reward not found")
    if is_same_referral_family(
        db,
        referrer_user_id=referrer_user_id,
        referred_client_id=reward.referred_client_id,
        referred_student_id=reward.referred_student_id,
    ) or _referrer_matches_reward_intake_family(db, referrer_user_id=referrer_user_id, reward=reward):
        raise ValueError("A family cannot refer itself")
    referrer = db.scalar(select(User).where(User.id == referrer_user_id, User.role == UserRole.CLIENT))
    if referrer is None:
        raise ValueError("Referrer client not found")
    reward.referrer_user_id = referrer_user_id
    reward.match_status = REFERRAL_MATCH_MANUAL
    reward.match_confidence = 100
    reward.status = REFERRAL_STATUS_AWAITING_PAYMENT
    reward.validated_at = utcnow()
    reward.metadata_json = {**(reward.metadata_json or {}), "validated_by": str(actor_user_id) if actor_user_id else None}
    reward.updated_at = utcnow()
    db.add(reward)
    if reward.referred_client_id is not None:
        try:
            send_referral_announcement_email(db, reward=reward)
        except Exception:
            logger.exception("Unable to send referral announcement email for reward=%s", reward.id)
    return reward


def _invoice_total(metadata: dict[str, object], *, currency: str) -> Decimal:
    totals = metadata.get("totals_by_currency")
    if not isinstance(totals, dict):
        return Decimal("0.00")
    raw = totals.get(currency) or totals.get(currency.upper()) or totals.get(currency.lower())
    return _decimal(raw, Decimal("0.00"))


def _manual_ids_from_metadata(metadata: dict[str, object], key: str) -> list[UUID]:
    raw = metadata.get(key)
    if not isinstance(raw, list):
        return []
    out: list[UUID] = []
    for item in raw:
        text = str(item or "").strip()
        if ":" in text:
            source, value = text.split(":", 1)
            if source.strip().upper() != "MANUAL":
                continue
            text = value.strip()
        try:
            out.append(UUID(text))
        except ValueError:
            continue
    return out


def quote_ids_from_invoice_metadata(db: Session, metadata: dict[str, object]) -> set[UUID]:
    manual_charge_ids = _manual_ids_from_metadata(metadata, "included_payment_keys")
    if not manual_charge_ids:
        return set()
    rows = db.scalars(select(ClientManualTransaction).where(ClientManualTransaction.id.in_(manual_charge_ids))).all()
    quote_ids: set[UUID] = set()
    for row in rows:
        if (row.category or "").strip().upper() == "PRE_REGISTRATION_DEPOSIT":
            continue
        match = re.match(r"^QUOTE:(?P<quote_id>[0-9a-fA-F-]{36}):", (row.reference or "").strip())
        if match is None:
            continue
        try:
            quote_ids.add(UUID(match.group("quote_id")))
        except ValueError:
            continue
    return quote_ids


def quote_ids_with_referral_ancestors(db: Session, quote_ids: set[UUID]) -> set[UUID]:
    out = set(quote_ids)
    pending = set(quote_ids)
    seen: set[UUID] = set()
    while pending:
        batch = pending - seen
        if not batch:
            break
        seen.update(batch)
        rewards_on_batch = set(
            db.scalars(select(ReferralReward.quote_id).where(ReferralReward.quote_id.in_(batch))).all()
        )
        rows = db.scalars(select(Quote).where(Quote.id.in_(batch))).all()
        pending = set()
        for row in rows:
            if row.id in rewards_on_batch:
                continue
            parent_id = row.parent_quote_id
            if parent_id is not None and parent_id not in out:
                out.add(parent_id)
                pending.add(parent_id)
    return out


def _paid_total_for_invoice(db: Session, metadata: dict[str, object], *, currency: str) -> Decimal:
    payment_ids = _manual_ids_from_metadata(metadata, "reconciled_manual_payment_ids")
    if not payment_ids:
        return Decimal("0.00")
    rows = db.scalars(
        select(ClientManualTransaction).where(
            ClientManualTransaction.id.in_(payment_ids),
            ClientManualTransaction.transaction_type == "PAYMENT",
        )
    ).all()
    total = Decimal("0.00")
    for row in rows:
        if (row.status or "").strip().upper() not in REFERRAL_PAID_STATUSES:
            continue
        if (row.currency or "EUR").strip().upper() != currency:
            continue
        total += abs(Decimal(row.total_incl_vat or 0))
    return total.quantize(Decimal("0.01"))


def evaluate_referrals_for_invoice(
    db: Session,
    *,
    client_id: UUID,
    note: ClientNoteEntry,
    metadata: dict[str, object],
) -> list[ReferralReward]:
    quote_ids = quote_ids_from_invoice_metadata(db, metadata)
    if not quote_ids:
        return []
    quote_ids = quote_ids_with_referral_ancestors(db, quote_ids)
    config = referral_program_config(db)
    if not config.enabled:
        return []
    currency = str(metadata.get("payment_currency") or config.currency or "EUR").strip().upper()[:3] or "EUR"
    invoice_total = _invoice_total(metadata, currency=currency)
    if invoice_total <= Decimal("0.00"):
        return []
    paid_total = _paid_total_for_invoice(db, metadata, currency=currency)
    granted: list[ReferralReward] = []
    for reward in db.scalars(select(ReferralReward).where(ReferralReward.quote_id.in_(quote_ids)).with_for_update()).all():
        if reward.status == REFERRAL_STATUS_CREDIT_GRANTED or reward.credit_transaction_id is not None:
            continue
        if reward.status not in {REFERRAL_STATUS_AWAITING_PAYMENT, REFERRAL_STATUS_DECLARED}:
            continue
        if reward.referrer_user_id is None:
            reward.status = REFERRAL_STATUS_NEEDS_REVIEW
            reward.updated_at = utcnow()
            db.add(reward)
            continue
        if reward.referred_client_id is None:
            reward.referred_client_id = client_id
        if refresh_referral_self_family_guard(db, reward):
            continue
        threshold_ratio = Decimal(reward.trigger_ratio or config.trigger_ratio).quantize(Decimal("0.0001"))
        if paid_total < (invoice_total * threshold_ratio).quantize(Decimal("0.01")):
            reward.trigger_invoice_note_id = note.id
            reward.metadata_json = {
                **(reward.metadata_json or {}),
                "last_invoice_total": f"{invoice_total:.2f}",
                "last_paid_total": f"{paid_total:.2f}",
                "last_threshold_ratio": f"{threshold_ratio:.4f}",
            }
            reward.updated_at = utcnow()
            db.add(reward)
            continue
        created = grant_referral_credit(
            db,
            reward=reward,
            invoice_note_id=note.id,
            invoice_total=invoice_total,
            paid_total=paid_total,
            currency=currency,
        )
        granted.append(created)
    return granted


def grant_referral_credit(
    db: Session,
    *,
    reward: ReferralReward,
    invoice_note_id: UUID,
    invoice_total: Decimal,
    paid_total: Decimal,
    currency: str,
) -> ReferralReward:
    if reward.credit_transaction_id is not None:
        return reward
    if reward.referrer_user_id is None:
        raise ValueError("Referral reward has no referrer")
    amount = Decimal(reward.reward_amount or 0).quantize(Decimal("0.01"))
    if amount <= Decimal("0.00"):
        reward.status = REFERRAL_STATUS_NEEDS_REVIEW
        reward.updated_at = utcnow()
        db.add(reward)
        return reward
    now = utcnow()
    referrer = db.scalar(select(User).where(User.id == reward.referrer_user_id))
    referred = db.scalar(select(User).where(User.id == reward.referred_client_id)) if reward.referred_client_id else None
    if _email_language(referrer) == "en":
        label = "Referral credit"
        description = "Credit generated automatically once the referred family's cashing threshold was reached."
        if referred is not None:
            label = f"Referral credit - {_display_name(referred)}"
    else:
        label = "Avoir parrainage"
        description = "Avoir genere automatiquement apres atteinte du seuil d encaissement du filleul."
        if referred is not None:
            label = f"Avoir parrainage - {_display_name(referred)}"
    transaction = ClientManualTransaction(
        user_id=reward.referrer_user_id,
        student_user_id=reward.referrer_user_id,
        actor_user_id=None,
        transaction_type="DISCOUNT",
        status="COMPLETED",
        label=label[:255],
        description=description,
        category="Parrainage",
        occurred_at=now,
        amount_excl_vat=Decimal("0.00") - amount,
        vat_rate=Decimal("0.000"),
        vat_amount=Decimal("0.00"),
        total_incl_vat=Decimal("0.00") - amount,
        currency=currency,
        reference=f"REFERRAL:{reward.id}",
        legal_entity_id=None,
        created_at=now,
        updated_at=now,
    )
    db.add(transaction)
    db.flush()
    reward.credit_transaction_id = transaction.id
    reward.trigger_invoice_note_id = invoice_note_id
    reward.status = REFERRAL_STATUS_CREDIT_GRANTED
    reward.credit_granted_at = now
    reward.metadata_json = {
        **(reward.metadata_json or {}),
        "trigger_invoice_total": f"{invoice_total:.2f}",
        "trigger_paid_total": f"{paid_total:.2f}",
        "trigger_currency": currency,
    }
    reward.updated_at = now
    db.add(reward)
    try:
        send_referral_credit_email(db, reward=reward)
    except Exception:
        logger.exception("Unable to send referral credit email for reward=%s", reward.id)
    return reward


def _email_context_for_reward(db: Session, reward: ReferralReward) -> tuple[User | None, User | None]:
    referrer = db.scalar(select(User).where(User.id == reward.referrer_user_id)) if reward.referrer_user_id else None
    referred = db.scalar(select(User).where(User.id == reward.referred_client_id)) if reward.referred_client_id else None
    return referrer, referred


def _email_language(user: User | None) -> str:
    return "en" if str(getattr(user, "preferred_language", "") or "").strip().lower() == "en" else "fr"


def send_referral_announcement_email(db: Session, *, reward: ReferralReward) -> str | None:
    config = referral_program_config(db)
    if not config.announcement_email_enabled or reward.announcement_email_sent_at is not None:
        return None
    referrer, referred = _email_context_for_reward(db, reward)
    if referrer is None or not referrer.email:
        return None
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    referrer_name = _display_name(referrer)
    language = _email_language(referrer)
    amount = Decimal(reward.reward_amount or 0).quantize(Decimal("0.01"))
    if language == "en":
        referred_name = _display_name(referred) or "a family"
        subject = "Your referral has been recorded"
        body = (
            f"Hello {referrer_name},\n\n"
            f"The {referred_name} family indicated that they discovered Piano Academie thanks to you.\n\n"
            f"Your referral has been recorded. A credit of {amount:.2f} {reward.currency} will be added "
            "to your account once your referred family reaches the required payment threshold.\n\n"
            "Thank you for your trust."
        )
    else:
        referred_name = _display_name(referred) or "une famille"
        subject = "Votre parrainage a bien ete enregistre"
        body = (
            f"Bonjour {referrer_name},\n\n"
            f"La famille {referred_name} a indique avoir decouvert Piano Academie grace a vous.\n\n"
            f"Votre parrainage est bien enregistre. Un avoir de {amount:.2f} {reward.currency} sera credite "
            "sur votre compte lorsque le seuil de reglement prevu aura ete atteint par votre filleul.\n\n"
            "Merci pour votre confiance."
        )
    message_id = send_email(
        to_email=referrer.email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context="REFERRAL_RECORDED",
        recipient_user_id=referrer.id,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
    )
    reward.announcement_email_sent_at = utcnow()
    reward.updated_at = reward.announcement_email_sent_at
    db.add(reward)
    return message_id


def send_referral_credit_email(db: Session, *, reward: ReferralReward) -> str | None:
    config = referral_program_config(db)
    if not config.credit_email_enabled or reward.credit_email_sent_at is not None:
        return None
    referrer, referred = _email_context_for_reward(db, reward)
    if referrer is None or not referrer.email:
        return None
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    referrer_name = _display_name(referrer)
    language = _email_language(referrer)
    amount = Decimal(reward.reward_amount or 0).quantize(Decimal("0.01"))
    if language == "en":
        referred_name = _display_name(referred) or "your referred family"
        subject = "Your referral credit is available"
        body = (
            f"Hello {referrer_name},\n\n"
            f"Your referral for {referred_name} is now validated.\n\n"
            f"A credit of {amount:.2f} {reward.currency} has been added to your account. "
            "It can be used on a future Piano Academie invoice.\n\n"
            "Thank you again for your recommendation."
        )
    else:
        referred_name = _display_name(referred) or "votre filleul"
        subject = "Votre avoir parrainage est disponible"
        body = (
            f"Bonjour {referrer_name},\n\n"
            f"Votre parrainage de {referred_name} est desormais valide.\n\n"
            f"Un avoir de {amount:.2f} {reward.currency} vient d etre credite sur votre compte. "
            "Il pourra etre utilise sur une prochaine facture Piano Academie.\n\n"
            "Merci encore pour votre recommandation."
        )
    message_id = send_email(
        to_email=referrer.email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context="REFERRAL_CREDIT_GRANTED",
        recipient_user_id=referrer.id,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
    )
    reward.credit_email_sent_at = utcnow()
    reward.updated_at = reward.credit_email_sent_at
    db.add(reward)
    return message_id


def referral_summary(reward: ReferralReward | None, db: Session | None = None) -> dict[str, object] | None:
    if reward is None:
        return None
    candidates = referral_match_candidates_for_reward(db, reward) if db is not None else reward.match_candidates_json or []
    return {
        "id": str(reward.id),
        "typeform_intake_id": str(reward.typeform_intake_id) if reward.typeform_intake_id else None,
        "quote_id": str(reward.quote_id) if reward.quote_id else None,
        "declared_referrer_text": reward.declared_referrer_text,
        "category": reward.category,
        "status": reward.status,
        "match_status": reward.match_status,
        "referrer_user_id": str(reward.referrer_user_id) if reward.referrer_user_id else None,
        "referred_client_id": str(reward.referred_client_id) if reward.referred_client_id else None,
        "reward_amount": f"{Decimal(reward.reward_amount or 0):.2f}",
        "currency": reward.currency,
        "trigger_ratio": f"{Decimal(reward.trigger_ratio or 0):.4f}",
        "credit_transaction_id": str(reward.credit_transaction_id) if reward.credit_transaction_id else None,
        "match_candidates": candidates,
    }
