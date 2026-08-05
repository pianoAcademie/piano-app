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
    PlanEntitlement,
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
SOURCE_CREDIT_TYPES = {
    "studio": "studio",
    "seance": "collective",
    "cours-collectif-en-ligne": "online",
    "cours-de-solfge": "solfege",
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
        grouped: Counter[tuple[str, str, datetime | None]] = Counter()
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
            grouped[(source_type, bucket, expiration_at)] += value
        credits.extend(
            SportigoCreditLot(source_type=source_type, bucket=bucket, value=value, expiration_at=expiration_at)
            for (source_type, bucket, expiration_at), value in grouped.items()
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


def _ensure_monthly_plan(db: Session, template: Plan) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.code == SPORTIGO_MONTHLY_PLAN_CODE).with_for_update())
    if plan is not None:
        return plan
    plan = Plan(
        code=SPORTIGO_MONTHLY_PLAN_CODE,
        name=f"Sportigo – {template.name}",
        kind=PlanKind.SUBSCRIPTION,
        credits_count=template.credits_count,
        pack_validity_months=template.pack_validity_months,
        monthly_price_value=template.monthly_price_value,
        price_tax_mode=template.price_tax_mode,
        monthly_price_excl_vat=template.monthly_price_excl_vat,
        currency_code=template.currency_code or "EUR",
        description="Abonnements migrés depuis Sportigo en août 2026.",
        billing_frequency=template.billing_frequency,
        booking_rights_policy=template.booking_rights_policy,
        retry_policy_id=template.retry_policy_id,
        notification_policy_id=template.notification_policy_id,
        signup_fee_value=0,
        signup_fee_excl_vat=0,
        credit_grants_relation=template.credit_grants_relation,
        is_private=True,
        options_json=list(template.options_json or []),
        payment_methods_json=list(template.payment_methods_json or []),
        restrictions_json=list(template.restrictions_json or []),
        active=True,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(plan)
    db.flush()
    for entitlement in db.scalars(select(PlanEntitlement).where(PlanEntitlement.plan_id == template.id)).all():
        db.add(PlanEntitlement(plan_id=plan.id, course_type_id=entitlement.course_type_id))
    for grant in db.scalars(select(PlanCreditGrant).where(PlanCreditGrant.plan_id == template.id)).all():
        db.add(PlanCreditGrant(plan_id=plan.id, credit_type_id=grant.credit_type_id, credits_count=grant.credits_count))
    return plan


def _pack_plan_code(lot: SportigoCreditLot) -> str:
    return f"{SPORTIGO_PACK_PREFIX}{lot.lot_key}"[:80]


def _ensure_pack_plan(db: Session, lot: SportigoCreditLot, credit_type: CreditType) -> Plan:
    code = _pack_plan_code(lot)
    plan = db.scalar(select(Plan).where(Plan.code == code).with_for_update())
    if plan is not None:
        return plan
    expiry_label = lot.expiration_at.date().strftime("%d/%m/%Y") if lot.expiration_at else "sans expiration"
    plan = Plan(
        code=code,
        name=f"Sportigo – {credit_type.name} – {expiry_label}",
        kind=PlanKind.PACK,
        credits_count=1,
        # The database restricts pack catalogue validity to 1-12 months. The
        # migrated balance keeps its real lifetime on the client subscription
        # (`ends_at`), including when Sportigo supplied no expiration date.
        pack_validity_months=12,
        currency_code="EUR",
        description="Solde de crédits migré depuis Sportigo en août 2026.",
        billing_frequency="one_off",
        is_private=True,
        options_json=[],
        payment_methods_json=[],
        restrictions_json=[],
        active=True,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(plan)
    db.flush()
    db.add(PlanCreditGrant(plan_id=plan.id, credit_type_id=credit_type.id, credits_count=1))
    return plan


def _catalog_objects(
    db: Session,
    *,
    template_plan_code: str,
    credit_type_codes: dict[str, str],
) -> tuple[Plan | None, dict[str, CreditType], list[str]]:
    errors: list[str] = []
    template = db.scalar(select(Plan).where(Plan.code == template_plan_code, Plan.active.is_(True)))
    if template is None or template.kind != PlanKind.SUBSCRIPTION:
        errors.append(f"Formule mensuelle introuvable ou non mensuelle : {template_plan_code}")
    credit_types: dict[str, CreditType] = {}
    for bucket, code in credit_type_codes.items():
        credit_type = db.scalar(select(CreditType).where(CreditType.code == code, CreditType.active.is_(True)))
        if credit_type is None:
            errors.append(f"Type de crédit introuvable pour {bucket} : {code}")
        else:
            credit_types[bucket] = credit_type
    return template, credit_types, errors


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
    credit_type_codes: dict[str, str],
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

    template, credit_types, catalog_errors = _catalog_objects(
        db,
        template_plan_code=template_plan_code,
        credit_type_codes=credit_type_codes,
    )
    out.errors.extend(catalog_errors)
    _preflight_rows(db, rows, out)
    if out.errors or dry_run:
        return out
    assert template is not None

    now = datetime.now(timezone.utc)
    group = _ensure_group(db)
    monthly_plan = _ensure_monthly_plan(db, template)
    all_pack_plans = {
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
                lesson_reminder_email_opt_in=False,
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
            started_at = row.monthly_started_at or now
            status_value = SubscriptionStatus.ACTIVE if activate else SubscriptionStatus.PENDING
            if subscription is None:
                subscription = ClientPlanSubscription(
                    user_id=user.id,
                    plan_id=monthly_plan.id,
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

        incoming_plan_codes: set[str] = set()
        for lot in row.credits:
            credit_type = credit_types[lot.bucket]
            plan = _ensure_pack_plan(db, lot, credit_type)
            all_pack_plans[plan.code] = plan
            incoming_plan_codes.add(plan.code)
            subscription = db.scalar(
                select(ClientPlanSubscription)
                .where(ClientPlanSubscription.user_id == user.id, ClientPlanSubscription.plan_id == plan.id)
                .with_for_update()
            )
            status_value = SubscriptionStatus.ACTIVE if activate else SubscriptionStatus.PENDING
            started_at = now
            ends_at = None
            if lot.expiration_at:
                ends_at = datetime.combine(lot.expiration_at.date(), time.max, tzinfo=lot.expiration_at.tzinfo or timezone.utc)
                if ends_at <= now:
                    status_value = SubscriptionStatus.EXPIRED
            if subscription is None:
                subscription = ClientPlanSubscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    status=status_value,
                    started_at=started_at,
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
                subscription.ends_at = ends_at
                subscription.credits_initial = lot.value
                subscription.credits_remaining = lot.value
                subscription.auto_renew = False
                subscription.bookings_blocked = False
                subscription.last_payment_status = "MIGRATED_CREDIT_BALANCE"
                db.add(subscription)
                out.credit_lots_updated += 1

        if all_pack_plans:
            existing_lots = db.execute(
                select(ClientPlanSubscription, Plan)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .where(
                    ClientPlanSubscription.user_id == user.id,
                    Plan.code.like(f"{SPORTIGO_PACK_PREFIX}%"),
                )
                .with_for_update()
            ).all()
            for existing, plan in existing_lots:
                if plan.code in incoming_plan_codes:
                    continue
                if (existing.credits_remaining or 0) != 0 or existing.status != SubscriptionStatus.EXPIRED:
                    existing.credits_remaining = 0
                    existing.status = SubscriptionStatus.EXPIRED
                    db.add(existing)
                    out.credit_lots_zeroed += 1

    db.commit()
    return out
