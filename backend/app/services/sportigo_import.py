from __future__ import annotations

import csv
import io
import json
import re
import secrets
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import CreditType
from app.models.client_group import ClientGroup, ClientGroupMembership
from app.models.plan import (
    ClientPlanSubscription,
    Plan,
    PlanCreditGrant,
    PlanKind,
    SubscriptionStatus,
)
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.schemas.sportigo import SportigoImportOut
from app.services.security import hash_password


SPORTIGO_GROUP_CODE = "SPORTIGO_2026"
SPORTIGO_GROUP_NAME = "Migration Sportigo 2026"
SPORTIGO_NOTE_BEGIN = "IMPORT_SOURCE:sportigo_2026"
SPORTIGO_NOTE_END = "END_IMPORT_SOURCE:sportigo_2026"
SPORTIGO_MONTHLY_PLAN_CODE = "SPORTIGO-MIG-MONTHLY-COLLECTIVE"
SPORTIGO_PACK_PREFIX = "SPORTIGO-MIG-PACK-"
SPORTIGO_MIGRATION_SOURCE_CODE = "SPORTIGO_2026_OPENING_BALANCE"
# Refunded accounts that must not be recreated by a later Sportigo refresh.
# Rona Kreiner's studio pack (member 1717363) was fully refunded.
SPORTIGO_EXCLUDED_MEMBER_IDS = {"1717363"}
SOURCE_CREDIT_TYPES = {
    "studio": "studio",
    "seance": "collective",
    "cours-collectif-en-ligne": "online",
    "cours-de-solfge": "solfege",
}
BUCKET_CREDIT_TYPE_CODES = {
    "studio": "CREDIT_STUDIO",
    "collective": "CREDIT_PIANO_ONSITE",
    "online": "CREDIT_PIANO_ONLINE",
    "solfege": "CREDIT_SOLFEGE_ONLINE",
}


def _clean(value: object) -> str:
    return str(value or "").replace("\ufeff", "").strip()


def _normalize_email(value: object) -> str | None:
    email = _clean(value).lower()
    return email if email and "@" in email else None


def _parse_bool(value: object) -> bool:
    return _clean(value).casefold() in {"1", "true", "yes", "oui", "y"}


def _parse_datetime(value: object) -> datetime | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: object) -> date | None:
    parsed = _parse_datetime(value)
    return parsed.date() if parsed else None


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class SportigoCreditLot:
    source_type: str
    bucket: str
    value: int
    expiration_at: datetime | None

    @property
    def lot_key(self) -> str:
        expiry = self.expiration_at.date().strftime("%Y%m%d") if self.expiration_at else "NOEXPIRY"
        return f"{self.bucket.upper()}-{expiry}"


@dataclass
class SportigoImportRow:
    row_number: int
    member_id: str
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    address_line: str | None
    postal_code: str | None
    city: str | None
    birth_date: date | None
    monthly: bool
    monthly_started_at: datetime | None
    monthly_next_payment_at: datetime | None
    monthly_last_payment_at: datetime | None
    monthly_payment_method: str | None
    credits: list[SportigoCreditLot] = field(default_factory=list)


def parse_sportigo_manifest(content: bytes) -> tuple[list[SportigoImportRow], list[str]]:
    text = _decode_csv(content)
    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = max((";", ",", "\t"), key=first_line.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    required = {"sportigo_member_id", "first_name", "last_name", "monthly", "credits_json"}
    headers = {_clean(header) for header in (reader.fieldnames or [])}
    missing = sorted(required - headers)
    if missing:
        return [], [f"Colonne(s) manquante(s) : {', '.join(missing)}"]

    rows: list[SportigoImportRow] = []
    errors: list[str] = []
    seen: set[str] = set()
    for row_number, raw in enumerate(reader, start=2):
        row = {_clean(key): _clean(value) for key, value in raw.items() if key is not None}
        member_id = _clean(row.get("sportigo_member_id"))
        first_name = _clean(row.get("first_name"))
        last_name = _clean(row.get("last_name"))
        if not member_id or not first_name or not last_name:
            errors.append(f"Ligne {row_number}: identifiant, prénom ou nom manquant.")
            continue
        if member_id in seen:
            errors.append(f"Ligne {row_number}: identifiant Sportigo {member_id} en double.")
            continue
        seen.add(member_id)
        if member_id in SPORTIGO_EXCLUDED_MEMBER_IDS:
            continue

        credits: list[SportigoCreditLot] = []
        raw_credits = _clean(row.get("credits_json")) or "[]"
        try:
            parsed_credits = json.loads(raw_credits)
        except json.JSONDecodeError:
            errors.append(f"Ligne {row_number}: credits_json invalide.")
            continue
        if not isinstance(parsed_credits, list):
            errors.append(f"Ligne {row_number}: credits_json doit être une liste.")
            continue
        grouped: Counter[tuple[str, str, date | None]] = Counter()
        for item in parsed_credits:
            if not isinstance(item, dict):
                errors.append(f"Ligne {row_number}: lot de crédits invalide.")
                continue
            source_type = _clean(item.get("source_type") or item.get("type"))
            bucket = SOURCE_CREDIT_TYPES.get(source_type)
            if bucket is None:
                errors.append(f"Ligne {row_number}: type de crédit Sportigo inconnu ({source_type}).")
                continue
            try:
                value = int(item.get("value") or 0)
            except (TypeError, ValueError):
                errors.append(f"Ligne {row_number}: quantité de crédits invalide ({source_type}).")
                continue
            if value < 0:
                errors.append(f"Ligne {row_number}: quantité de crédits négative ({source_type}).")
                continue
            expiration_at = _parse_datetime(item.get("expiration_date"))
            grouped[(source_type, bucket, expiration_at.date() if expiration_at else None)] += value
        credits.extend(
            SportigoCreditLot(
                source_type=source_type,
                bucket=bucket,
                value=value,
                expiration_at=datetime.combine(expiration_date, time.min, tzinfo=timezone.utc) if expiration_date else None,
            )
            for (source_type, bucket, expiration_date), value in grouped.items()
            if value > 0
        )

        monthly = _parse_bool(row.get("monthly"))
        next_payment = _parse_datetime(row.get("monthly_next_payment_at"))
        if monthly and next_payment is None:
            errors.append(f"Ligne {row_number}: prochaine échéance mensuelle manquante.")
            continue
        rows.append(
            SportigoImportRow(
                row_number=row_number,
                member_id=member_id,
                first_name=first_name,
                last_name=last_name,
                email=_normalize_email(row.get("email")),
                phone=_clean(row.get("phone")) or None,
                address_line=_clean(row.get("address_line")) or None,
                postal_code=_clean(row.get("postal_code")) or None,
                city=_clean(row.get("city")) or None,
                birth_date=_parse_date(row.get("birth_date")),
                monthly=monthly,
                monthly_started_at=_parse_datetime(row.get("monthly_started_at")),
                monthly_next_payment_at=next_payment,
                monthly_last_payment_at=_parse_datetime(row.get("monthly_last_payment_at")),
                monthly_payment_method=_clean(row.get("monthly_payment_method")) or None,
                credits=credits,
            )
        )
    return rows, errors


def _sportigo_note(member_id: str, batch_reference: str) -> str:
    return "\n".join(
        [
            SPORTIGO_NOTE_BEGIN,
            f"SPORTIGO_MEMBER_ID:{member_id}",
            f"SPORTIGO_LAST_BATCH:{batch_reference}",
            SPORTIGO_NOTE_END,
        ]
    )


def _merge_note(existing: str | None, block: str) -> str:
    current = _clean(existing)
    pattern = re.compile(
        rf"\n?{re.escape(SPORTIGO_NOTE_BEGIN)}.*?{re.escape(SPORTIGO_NOTE_END)}",
        re.DOTALL,
    )
    retained = pattern.sub("", current).strip()
    return f"{retained}\n\n{block}" if retained else block


def _find_by_sportigo_id(db: Session, member_id: str, *, lock: bool) -> User | None:
    stmt = (
        select(User)
        .where(User.role == UserRole.CLIENT, User.private_note.ilike(f"%SPORTIGO_MEMBER_ID:{member_id}%"))
        .order_by(User.created_at.asc())
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _find_by_email(db: Session, email: str | None, *, lock: bool) -> User | None:
    if not email:
        return None
    stmt = select(User).where(func.lower(User.email) == email.lower()).limit(1)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _billing_method(source: str | None) -> str:
    normalized = _clean(source).casefold()
    return "SEPA_DEBIT" if "sepa" in normalized else "CARD_ONLINE"


def _ensure_group(db: Session) -> ClientGroup:
    group = db.scalar(select(ClientGroup).where(ClientGroup.code == SPORTIGO_GROUP_CODE).with_for_update())
    if group is None:
        group = ClientGroup(code=SPORTIGO_GROUP_CODE, name=SPORTIGO_GROUP_NAME, active=True, updated_at=datetime.now(timezone.utc))
        db.add(group)
        db.flush()
    return group


def _ensure_group_membership(db: Session, user_id: UUID, group_id: UUID) -> None:
    existing = db.scalar(
        select(ClientGroupMembership.id).where(
            ClientGroupMembership.user_id == user_id,
            ClientGroupMembership.group_id == group_id,
        )
    )
    if existing is None:
        db.add(ClientGroupMembership(user_id=user_id, group_id=group_id))


def _pack_plan_code(lot: SportigoCreditLot) -> str:
    return f"{SPORTIGO_PACK_PREFIX}{lot.lot_key}"[:80]


def _catalog_objects(
    db: Session,
    *,
    template_plan_code: str,
    pack_plan_codes: dict[str, str],
) -> tuple[Plan | None, dict[str, Plan], list[str]]:
    errors: list[str] = []
    template = db.scalar(select(Plan).where(Plan.code == template_plan_code, Plan.active.is_(True)))
    if template is None or template.kind != PlanKind.SUBSCRIPTION:
        errors.append(f"Formule mensuelle introuvable ou non mensuelle : {template_plan_code}")
    pack_plans: dict[str, Plan] = {}
    for bucket, code in pack_plan_codes.items():
        plan = db.scalar(select(Plan).where(Plan.code == code, Plan.active.is_(True)))
        if plan is None or plan.kind != PlanKind.PACK:
            errors.append(f"Carnet catalogue introuvable pour {bucket} : {code}")
            continue
        expected_credit_code = BUCKET_CREDIT_TYPE_CODES[bucket]
        supports_credit = db.scalar(
            select(PlanCreditGrant.id)
            .join(CreditType, CreditType.id == PlanCreditGrant.credit_type_id)
            .where(PlanCreditGrant.plan_id == plan.id, CreditType.code == expected_credit_code)
        )
        if supports_credit is None:
            errors.append(
                f"Le carnet {plan.name} ne porte pas le type de crédit requis pour {bucket} ({expected_credit_code})."
            )
            continue
        pack_plans[bucket] = plan
    return template, pack_plans, errors


def _lot_ends_at(lot: SportigoCreditLot) -> datetime | None:
    if lot.expiration_at is None:
        return None
    return datetime.combine(lot.expiration_at.date(), time.max, tzinfo=timezone.utc)


def _preflight_rows(db: Session, rows: Iterable[SportigoImportRow], out: SportigoImportOut) -> None:
    for row in rows:
        by_id = _find_by_sportigo_id(db, row.member_id, lock=False)
        by_email = _find_by_email(db, row.email, lock=False)
        if by_id is not None:
            out.clients_reused_by_sportigo_id += 1
            if by_email is not None and by_email.id != by_id.id:
                out.errors.append(f"Ligne {row.row_number}: l'identifiant Sportigo et l'email pointent vers deux comptes différents.")
        elif by_email is not None:
            if by_email.role != UserRole.CLIENT or by_email.client_kind != ClientKind.ADULT:
                out.errors.append(f"Ligne {row.row_number}: email déjà utilisé par un compte incompatible ({row.email}).")
            else:
                out.clients_reused_by_email += 1
        else:
            out.clients_created += 1


def run_sportigo_import(
    db: Session,
    rows: list[SportigoImportRow],
    *,
    dry_run: bool,
    activate: bool,
    batch_reference: str,
    template_plan_code: str,
    pack_plan_codes: dict[str, str],
) -> SportigoImportOut:
    out = SportigoImportOut(
        dry_run=dry_run,
        activate=activate,
        batch_reference=batch_reference,
        rows_seen=len(rows),
        rows_valid=len(rows),
        imported_clients_total=len(rows),
        imported_monthly_total=sum(1 for row in rows if row.monthly),
        imported_credit_clients_total=sum(1 for row in rows if row.credits),
    )
    for row in rows:
        for lot in row.credits:
            if lot.bucket == "studio":
                out.studio_credits_total += lot.value
            elif lot.bucket == "collective":
                out.collective_credits_total += lot.value
            elif lot.bucket == "online":
                out.online_credits_total += lot.value
            elif lot.bucket == "solfege":
                out.solfege_credits_total += lot.value

    template, pack_plans, catalog_errors = _catalog_objects(
        db,
        template_plan_code=template_plan_code,
        pack_plan_codes=pack_plan_codes,
    )
    out.errors.extend(catalog_errors)
    _preflight_rows(db, rows, out)
    if out.errors or dry_run:
        return out
    assert template is not None

    now = datetime.now(timezone.utc)
    group = _ensure_group(db)
    # Monthly subscribers use the existing catalogue formula selected by the
    # administrator. Older staged imports created a private Sportigo clone;
    # those subscriptions are moved to the catalogue formula below.
    monthly_plan = template
    legacy_monthly_plan = db.scalar(
        select(Plan).where(Plan.code == SPORTIGO_MONTHLY_PLAN_CODE).with_for_update()
    )
    if legacy_monthly_plan is not None and legacy_monthly_plan.id == monthly_plan.id:
        legacy_monthly_plan = None
    legacy_pack_plans = {
        plan.code: plan
        for plan in db.scalars(select(Plan).where(Plan.code.like(f"{SPORTIGO_PACK_PREFIX}%"))).all()
    }

    for row in rows:
        user = _find_by_sportigo_id(db, row.member_id, lock=True)
        reused_by_email = False
        if user is None:
            user = _find_by_email(db, row.email, lock=True)
            reused_by_email = user is not None
        if user is None:
            email = row.email or f"sportigo-{row.member_id}@no-email.local"
            user = User(
                email=email,
                contact_email=row.email,
                hashed_password=hash_password(secrets.token_urlsafe(24)),
                role=UserRole.CLIENT,
                client_kind=ClientKind.ADULT,
                client_status=ClientStatus.ACTIVE if activate else ClientStatus.PENDING,
                is_active=activate,
                first_name=row.first_name,
                last_name=row.last_name,
                phone=row.phone,
                mobile_phone_1=row.phone,
                address_line=row.address_line,
                postal_code=row.postal_code,
                city=row.city,
                birth_date=row.birth_date,
                address_country="FR",
                residence_country="FR",
                preferred_language="fr",
                preferred_currency="EUR",
                timezone="Europe/Paris",
                portal_contact_visible=True,
                email_opt_in=False,
                sms_opt_in=False,
                lesson_reminder_email_opt_in=True,
                lesson_reminder_sms_opt_in=False,
                private_note=_sportigo_note(row.member_id, batch_reference),
                updated_at=now,
            )
            db.add(user)
            db.flush()
        else:
            changed = False
            for attr, value in (
                ("first_name", row.first_name),
                ("last_name", row.last_name),
                ("phone", row.phone),
                ("mobile_phone_1", row.phone),
                ("address_line", row.address_line),
                ("postal_code", row.postal_code),
                ("city", row.city),
                ("birth_date", row.birth_date),
            ):
                if value and not getattr(user, attr, None):
                    setattr(user, attr, value)
                    changed = True
            note = _merge_note(user.private_note, _sportigo_note(row.member_id, batch_reference))
            if note != (user.private_note or ""):
                user.private_note = note
                changed = True
            if activate and (user.client_status == ClientStatus.PENDING or not user.is_active):
                user.client_status = ClientStatus.ACTIVE
                user.is_active = True
                changed = True
            if changed:
                user.updated_at = now
                db.add(user)
                out.clients_updated += 1
            if reused_by_email:
                out.clients_reused_by_email += 0  # already counted during preflight
        _ensure_group_membership(db, user.id, group.id)

        if row.monthly:
            subscription = db.scalar(
                select(ClientPlanSubscription)
                .where(ClientPlanSubscription.user_id == user.id, ClientPlanSubscription.plan_id == monthly_plan.id)
                .with_for_update()
            )
            legacy_subscription = None
            if legacy_monthly_plan is not None:
                legacy_subscription = db.scalar(
                    select(ClientPlanSubscription)
                    .where(
                        ClientPlanSubscription.user_id == user.id,
                        ClientPlanSubscription.plan_id == legacy_monthly_plan.id,
                    )
                    .with_for_update()
                )
            if subscription is None and legacy_subscription is not None:
                legacy_subscription.plan_id = monthly_plan.id
                db.add(legacy_subscription)
                subscription = legacy_subscription
            elif subscription is not None and legacy_subscription is not None and legacy_subscription.id != subscription.id:
                db.delete(legacy_subscription)
            started_at = row.monthly_started_at or now
            status_value = SubscriptionStatus.ACTIVE if activate else SubscriptionStatus.PENDING
            if subscription is None:
                subscription = ClientPlanSubscription(
                    user_id=user.id,
                    plan_id=monthly_plan.id,
                    migration_source_code=SPORTIGO_MIGRATION_SOURCE_CODE,
                    status=status_value,
                    started_at=started_at,
                    ends_at=row.monthly_next_payment_at,
                    auto_renew=False,
                    bookings_blocked=False,
                    billing_method_code=_billing_method(row.monthly_payment_method),
                    next_payment_at=row.monthly_next_payment_at,
                    current_period_start=started_at,
                    current_period_end=row.monthly_next_payment_at,
                    last_payment_at=row.monthly_last_payment_at,
                    last_successful_charge_at=row.monthly_last_payment_at,
                    last_payment_status="MIGRATED_PAYMENT_METHOD_REQUIRED",
                    payment_provider_code="STRIPE",
                    payment_method_setup_required=True,
                    forfait_loyalty_discount_per_hour_ttc=Decimal("0.00"),
                    forfait_family_discount_per_hour_ttc=Decimal("0.00"),
                    forfait_short_commitment_supplement_per_hour_ttc=Decimal("0.00"),
                )
                db.add(subscription)
                out.subscriptions_created += 1
            else:
                subscription.status = status_value
                subscription.migration_source_code = SPORTIGO_MIGRATION_SOURCE_CODE
                subscription.started_at = started_at
                subscription.ends_at = row.monthly_next_payment_at
                subscription.next_payment_at = row.monthly_next_payment_at
                subscription.current_period_start = started_at
                subscription.current_period_end = row.monthly_next_payment_at
                subscription.last_payment_at = row.monthly_last_payment_at
                subscription.last_successful_charge_at = row.monthly_last_payment_at
                subscription.billing_method_code = _billing_method(row.monthly_payment_method)
                subscription.auto_renew = False
                subscription.bookings_blocked = False
                subscription.payment_provider_code = "STRIPE"
                subscription.payment_method_setup_required = True
                subscription.last_payment_status = "MIGRATED_PAYMENT_METHOD_REQUIRED"
                db.add(subscription)
                out.subscriptions_updated += 1

        incoming_subscription_ids: set[UUID] = set()
        for lot in row.credits:
            plan = pack_plans[lot.bucket]
            ends_at = _lot_ends_at(lot)
            end_condition = (
                ClientPlanSubscription.ends_at.is_(None)
                if ends_at is None
                else ClientPlanSubscription.ends_at == ends_at
            )
            subscription = db.scalar(
                select(ClientPlanSubscription)
                .where(
                    ClientPlanSubscription.user_id == user.id,
                    ClientPlanSubscription.plan_id == plan.id,
                    ClientPlanSubscription.last_payment_status == "MIGRATED_CREDIT_BALANCE",
                    end_condition,
                )
                .with_for_update()
            )
            legacy_plan = legacy_pack_plans.get(_pack_plan_code(lot))
            legacy_subscription = None
            if legacy_plan is not None:
                legacy_subscription = db.scalar(
                    select(ClientPlanSubscription)
                    .where(
                        ClientPlanSubscription.user_id == user.id,
                        ClientPlanSubscription.plan_id == legacy_plan.id,
                    )
                    .with_for_update()
                )
            if subscription is None and legacy_subscription is not None:
                legacy_subscription.plan_id = plan.id
                subscription = legacy_subscription
            elif subscription is not None and legacy_subscription is not None and legacy_subscription.id != subscription.id:
                db.delete(legacy_subscription)
            status_value = SubscriptionStatus.ACTIVE if activate else SubscriptionStatus.PENDING
            if ends_at is not None and ends_at <= now:
                status_value = SubscriptionStatus.EXPIRED
            if subscription is None:
                subscription = ClientPlanSubscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    migration_source_code=SPORTIGO_MIGRATION_SOURCE_CODE,
                    status=status_value,
                    started_at=now,
                    ends_at=ends_at,
                    credits_initial=lot.value,
                    credits_remaining=lot.value,
                    auto_renew=False,
                    bookings_blocked=False,
                    last_payment_status="MIGRATED_CREDIT_BALANCE",
                    forfait_loyalty_discount_per_hour_ttc=Decimal("0.00"),
                    forfait_family_discount_per_hour_ttc=Decimal("0.00"),
                    forfait_short_commitment_supplement_per_hour_ttc=Decimal("0.00"),
                )
                db.add(subscription)
                out.credit_lots_created += 1
            else:
                subscription.status = status_value
                subscription.migration_source_code = SPORTIGO_MIGRATION_SOURCE_CODE
                subscription.ends_at = ends_at
                subscription.credits_initial = lot.value
                subscription.credits_remaining = lot.value
                subscription.auto_renew = False
                subscription.bookings_blocked = False
                subscription.last_payment_status = "MIGRATED_CREDIT_BALANCE"
                db.add(subscription)
                out.credit_lots_updated += 1
            db.flush()
            incoming_subscription_ids.add(subscription.id)

        if legacy_pack_plans or row.credits:
            existing_lots = db.execute(
                select(ClientPlanSubscription, Plan)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .where(
                    ClientPlanSubscription.user_id == user.id,
                    Plan.kind == PlanKind.PACK,
                    ClientPlanSubscription.last_payment_status == "MIGRATED_CREDIT_BALANCE",
                )
                .with_for_update()
            ).all()
            for existing, _plan in existing_lots:
                if existing.id in incoming_subscription_ids:
                    continue
                # These rows are exclusively identified by the migration
                # marker. Removing obsolete/duplicate staging rows prevents
                # technical Sportigo products from lingering in the client's
                # finished-product history after the canonical pack is linked.
                db.delete(existing)
                out.credit_lots_zeroed += 1

    if legacy_monthly_plan is not None:
        db.flush()
        remaining_legacy_subscriptions = db.scalar(
            select(func.count(ClientPlanSubscription.id)).where(
                ClientPlanSubscription.plan_id == legacy_monthly_plan.id
            )
        )
        if int(remaining_legacy_subscriptions or 0) == 0 and legacy_monthly_plan.active:
            legacy_monthly_plan.active = False
            legacy_monthly_plan.updated_at = now
            db.add(legacy_monthly_plan)

    for legacy_plan in legacy_pack_plans.values():
        if legacy_plan.active:
            legacy_plan.active = False
            legacy_plan.updated_at = now
            db.add(legacy_plan)

    db.commit()
    return out
