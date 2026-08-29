from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, SessionStatus
from app.models.family import ClientFamilyLink
from app.models.plan import ClientPlanSubscription, Plan, SubscriptionStatus
from app.models.quote import Prospect
from app.models.user import ClientKind, User, UserRole
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.notifications.domain.constants import SOURCE_SCHEDULER
from app.services.notifications.infrastructure.repository import (
    append_job_run_log,
    finish_job_run,
    get_job_cursor,
    start_job_run,
    upsert_job_cursor,
)
from app.services.shared.locks.redis_lock import redis_lock

JOB_NAME = "zendesk_contact_sync"
FULL_CURSOR_NAME = "zendesk_contact_sync_full"
JOB_LOCK_KEY = "lock:job:zendesk_contact_sync"
DEFAULT_LIMIT = 10_000
ACTIVE_BOOKING_STATUSES = (
    BookingStatus.BOOKED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)
CURRENT_SUBSCRIPTION_STATUSES = (
    SubscriptionStatus.PENDING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAYMENT_ALERT,
    SubscriptionStatus.PRE_TERMINATION,
    SubscriptionStatus.PAUSED,
)
SUBSCRIPTION_STATUS_LABELS = {
    SubscriptionStatus.PENDING: "en attente",
    SubscriptionStatus.ACTIVE: "active",
    SubscriptionStatus.PAYMENT_ALERT: "alerte paiement",
    SubscriptionStatus.PRE_TERMINATION: "pré-résiliation",
    SubscriptionStatus.PAUSED: "suspendue",
}
FRENCH_WEEKDAYS = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)
USER_FIELDS = (
    {
        "key": "piano_app_contact_type",
        "type": "text",
        "title": "Type de contact Piano Académie",
        "description": "Client/responsable ou prospect synchronisé depuis Piano Académie.",
    },
    {
        "key": "piano_app_children",
        "type": "textarea",
        "title": "Enfants inscrits Piano Académie",
        "description": "Noms des enfants liés au responsable dans Piano Académie.",
    },
    {
        "key": "piano_app_schedule",
        "type": "textarea",
        "title": "Créneaux des enfants Piano Académie",
        "description": "Créneaux futurs récurrents des enfants inscrits.",
    },
    {
        "key": "piano_app_locations",
        "type": "text",
        "title": "Lieux Piano Académie",
        "description": "Lieux de cours futurs des enfants inscrits.",
    },
    {
        "key": "piano_app_adult_student",
        "type": "checkbox",
        "title": "Adulte élève Piano Académie",
        "description": "Indique si cet adulte suit lui-même une formule ou possède un cours futur.",
    },
    {
        "key": "piano_app_adult_plans",
        "type": "textarea",
        "title": "Formules en cours de l’adulte",
        "description": "Formules en cours rattachées directement à l’adulte élève.",
    },
    {
        "key": "piano_app_profile_url",
        "type": "text",
        "title": "Fiche Piano Académie",
        "description": "Lien direct vers la fiche dans le portail administrateur.",
    },
    {
        "key": "piano_app_status",
        "type": "text",
        "title": "Statut Piano Académie",
        "description": "Statut du client ou du prospect dans Piano Académie.",
    },
    {
        "key": "piano_app_last_sync",
        "type": "text",
        "title": "Dernière synchro Piano Académie",
        "description": "Date de dernière synchronisation de cette fiche.",
    },
)


@dataclass(frozen=True)
class ZendeskContactCandidate:
    source_type: str
    source_id: UUID
    external_id: str
    name: str
    email: str
    alternate_emails: tuple[str, ...]
    phones: tuple[str, ...]
    status: str
    children: tuple[str, ...]
    schedule: tuple[str, ...]
    locations: tuple[str, ...]
    adult_is_student: bool
    adult_plans: tuple[str, ...]
    profile_url: str


@dataclass(frozen=True)
class ZendeskSyncResult:
    checked: int
    processed: int
    created_or_updated: int
    skipped: int
    failed: int
    conflicts: int
    dry_run: bool
    job_run_id: UUID | None


def zendesk_credentials_complete() -> bool:
    return bool(
        settings.zendesk_subdomain.strip()
        and settings.zendesk_admin_email.strip()
        and settings.zendesk_api_token.strip()
    )


def normalize_email(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    return candidate or None


def normalize_phone(value: str | None, *, default_country_code: str = "FR") -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    raw = raw.replace("(0)", "")
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    if default_country_code.upper() == "FR" and len(digits) == 10 and digits.startswith("0"):
        return f"+33{digits[1:]}"
    if default_country_code.upper() == "FR" and len(digits) == 11 and digits.startswith("33"):
        return f"+{digits}"
    # A local number outside France cannot be made unambiguous without a
    # country-specific dialling rule. Skipping it is safer than attaching an
    # incorrect caller identity in Zendesk.
    return None


def _display_name(first_name: str | None, last_name: str | None, fallback: str) -> str:
    name = " ".join(part.strip() for part in (first_name or "", last_name or "") if part.strip())
    return name or fallback


def _truncate_field(value: str, *, limit: int = 250) -> str:
    cleaned = "\n".join(part.strip() for part in value.splitlines() if part.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _local_session_times(session_obj: CourseSession, location: Location) -> tuple[datetime, datetime]:
    timezone_name = session_obj.timezone or location.timezone or "Europe/Paris"
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = ZoneInfo("Europe/Paris")
    start = session_obj.start_at_utc
    end = session_obj.end_at_utc
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return start.astimezone(timezone), end.astimezone(timezone)


def _changed_adult_ids(db: Session, *, since: datetime | None) -> set[UUID] | None:
    if since is None:
        return None

    child = aliased(User)
    adult_ids = set(
        db.scalars(
            select(User.id).where(
                User.role == UserRole.CLIENT,
                User.client_kind == ClientKind.ADULT,
                User.updated_at >= since,
            )
        ).all()
    )
    adult_ids.update(
        db.scalars(select(ClientFamilyLink.adult_user_id).where(ClientFamilyLink.updated_at >= since)).all()
    )
    adult_ids.update(
        db.scalars(
            select(ClientFamilyLink.adult_user_id)
            .join(child, child.id == ClientFamilyLink.child_user_id)
            .where(child.updated_at >= since)
        ).all()
    )
    adult_ids.update(
        db.scalars(
            select(ClientFamilyLink.adult_user_id)
            .join(Booking, Booking.user_id == ClientFamilyLink.child_user_id)
            .where(or_(Booking.booked_at >= since, Booking.cancelled_at >= since))
        ).all()
    )
    adult_ids.update(
        db.scalars(
            select(ClientFamilyLink.adult_user_id)
            .join(Booking, Booking.user_id == ClientFamilyLink.child_user_id)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(CourseSession.updated_at >= since)
        ).all()
    )
    adult_ids.update(
        db.scalars(
            select(ClientPlanSubscription.user_id).where(ClientPlanSubscription.created_at >= since)
        ).all()
    )
    adult_ids.update(
        db.scalars(
            select(ClientPlanSubscription.user_id)
            .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
            .where(Plan.updated_at >= since)
        ).all()
    )
    adult_ids.update(
        db.scalars(
            select(Booking.user_id)
            .join(User, User.id == Booking.user_id)
            .where(
                User.client_kind == ClientKind.ADULT,
                or_(Booking.booked_at >= since, Booking.cancelled_at >= since),
            )
        ).all()
    )
    return adult_ids


def _adult_learning_context(
    db: Session,
    *,
    adult_ids: set[UUID],
    now: datetime,
) -> tuple[set[UUID], dict[UUID, tuple[str, ...]]]:
    if not adult_ids:
        return set(), {}

    student_adult_ids: set[UUID] = set()
    plans_by_adult: dict[UUID, set[str]] = {}
    subscription_rows = db.execute(
        select(ClientPlanSubscription.user_id, ClientPlanSubscription.status, Plan.name)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(
            ClientPlanSubscription.user_id.in_(adult_ids),
            ClientPlanSubscription.status.in_(CURRENT_SUBSCRIPTION_STATUSES),
            or_(ClientPlanSubscription.ends_at.is_(None), ClientPlanSubscription.ends_at >= now),
        )
        .order_by(Plan.name.asc())
    ).all()
    for adult_id, status, plan_name in subscription_rows:
        student_adult_ids.add(adult_id)
        plans_by_adult.setdefault(adult_id, set()).add(
            f"{plan_name} ({SUBSCRIPTION_STATUS_LABELS.get(status, status.value.lower())})"
        )

    future_booking_adult_ids = db.scalars(
        select(Booking.user_id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.user_id.in_(adult_ids),
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.end_at_utc >= now,
        )
        .distinct()
    ).all()
    student_adult_ids.update(future_booking_adult_ids)
    return student_adult_ids, {
        adult_id: tuple(sorted(plan_names))
        for adult_id, plan_names in plans_by_adult.items()
    }


def _family_context(
    db: Session,
    *,
    adult_ids: set[UUID],
    now: datetime,
) -> tuple[dict[UUID, tuple[str, ...]], dict[UUID, tuple[str, ...]], dict[UUID, tuple[str, ...]]]:
    if not adult_ids:
        return {}, {}, {}

    child = aliased(User)
    family_rows = db.execute(
        select(ClientFamilyLink.adult_user_id, child)
        .join(child, child.id == ClientFamilyLink.child_user_id)
        .where(ClientFamilyLink.adult_user_id.in_(adult_ids), child.account_deleted_at.is_(None))
        .order_by(child.last_name.asc(), child.first_name.asc())
    ).all()

    children_by_adult: dict[UUID, list[str]] = {}
    child_to_adults: dict[UUID, set[UUID]] = {}
    child_names: dict[UUID, str] = {}
    child_ids: set[UUID] = set()
    for adult_id, child_row in family_rows:
        child_ids.add(child_row.id)
        child_to_adults.setdefault(child_row.id, set()).add(adult_id)
        child_name = _display_name(child_row.first_name, child_row.last_name, "Enfant")
        child_names[child_row.id] = child_name
        if child_name not in children_by_adult.setdefault(adult_id, []):
            children_by_adult[adult_id].append(child_name)

    schedules_by_adult: dict[UUID, set[str]] = {}
    locations_by_adult: dict[UUID, set[str]] = {}
    if child_ids:
        schedule_rows = db.execute(
            select(Booking.user_id, CourseSession, CourseType, Location)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                Booking.user_id.in_(child_ids),
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                CourseSession.status != SessionStatus.CANCELLED,
                CourseSession.end_at_utc >= now,
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()

        # Future occurrences of a recurring course are intentionally folded
        # into one readable weekly slot per child.
        for child_id, session_obj, course_type, location in schedule_rows:
            start, end = _local_session_times(session_obj, location)
            line = (
                f"{child_names.get(child_id, 'Enfant')} — {FRENCH_WEEKDAYS[start.weekday()]} "
                f"{start:%H:%M}-{end:%H:%M} — {location.name} — {course_type.name}"
            )
            for adult_id in child_to_adults.get(child_id, set()):
                schedules_by_adult.setdefault(adult_id, set()).add(line)
                locations_by_adult.setdefault(adult_id, set()).add(location.name)

    children = {adult_id: tuple(names) for adult_id, names in children_by_adult.items()}
    schedules = {adult_id: tuple(sorted(lines)) for adult_id, lines in schedules_by_adult.items()}
    locations = {adult_id: tuple(sorted(names)) for adult_id, names in locations_by_adult.items()}
    return children, schedules, locations


def build_zendesk_contact_candidates(
    db: Session,
    *,
    now: datetime,
    since: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[ZendeskContactCandidate]:
    changed_adult_ids = _changed_adult_ids(db, since=since)
    adult_query = select(User).where(
        User.role == UserRole.CLIENT,
        User.client_kind == ClientKind.ADULT,
        User.account_deleted_at.is_(None),
    )
    if changed_adult_ids is not None:
        adult_query = adult_query.where(User.id.in_(changed_adult_ids))
    adults = list(db.scalars(adult_query.order_by(User.updated_at.asc(), User.id.asc()).limit(limit)).all())
    adult_ids = {adult.id for adult in adults}
    children, schedules, locations = _family_context(db, adult_ids=adult_ids, now=now)
    student_adult_ids, adult_plans = _adult_learning_context(db, adult_ids=adult_ids, now=now)
    base_url = resolve_frontend_base_url(db).strip().rstrip("/")

    candidates: list[ZendeskContactCandidate] = []
    # This global set prevents a changed prospect from replacing the external
    # id of an already existing (but unchanged) client with the same email.
    client_emails: set[str] = {
        email
        for row in db.execute(
            select(User.email, User.contact_email).where(
                User.role == UserRole.CLIENT,
                User.client_kind == ClientKind.ADULT,
                User.account_deleted_at.is_(None),
            )
        ).all()
        for email in (normalize_email(row.email), normalize_email(row.contact_email))
        if email
    }
    for adult in adults:
        # The account email is the stable unique identity in Piano Académie and
        # therefore the safest match for a Zendesk user that may already exist.
        # The communication email is added just below as a secondary identity.
        email = normalize_email(adult.email) or normalize_email(adult.contact_email)
        if not email:
            continue
        alternate_emails = tuple(
            candidate
            for candidate in dict.fromkeys(
                filter(None, (normalize_email(adult.email), normalize_email(adult.contact_email)))
            )
            if candidate != email
        )
        phones = tuple(
            dict.fromkeys(
                filter(
                    None,
                    (
                        normalize_phone(adult.mobile_phone_1, default_country_code=adult.address_country),
                        normalize_phone(adult.phone, default_country_code=adult.address_country),
                        normalize_phone(adult.mobile_phone_2, default_country_code=adult.address_country),
                        normalize_phone(adult.home_phone, default_country_code=adult.address_country),
                    ),
                )
            )
        )
        candidates.append(
            ZendeskContactCandidate(
                source_type="client",
                source_id=adult.id,
                external_id=f"piano-client:{adult.id}",
                name=_display_name(adult.first_name, adult.last_name, email),
                email=email,
                alternate_emails=alternate_emails,
                phones=phones,
                status=adult.client_status.value,
                children=children.get(adult.id, ()),
                schedule=schedules.get(adult.id, ()),
                locations=locations.get(adult.id, ()),
                adult_is_student=adult.id in student_adult_ids,
                adult_plans=adult_plans.get(adult.id, ()),
                profile_url=f"{base_url}/admin/clients/{adult.id}",
            )
        )

    remaining = max(limit - len(candidates), 0)
    if remaining:
        prospect_query = select(Prospect).where(
            Prospect.linked_client_id.is_(None),
            func.lower(func.coalesce(Prospect.meta["prospect_type"].astext, "adult")) != "child",
        )
        if since is not None:
            prospect_query = prospect_query.where(Prospect.updated_at >= since)
        prospects = db.scalars(prospect_query.order_by(Prospect.updated_at.asc(), Prospect.id.asc()).limit(remaining)).all()
        for prospect in prospects:
            email = normalize_email(prospect.email)
            if not email or email in client_emails:
                continue
            client_emails.add(email)
            phone = normalize_phone(prospect.phone)
            candidates.append(
                ZendeskContactCandidate(
                    source_type="prospect",
                    source_id=prospect.id,
                    external_id=f"piano-prospect:{prospect.id}",
                    name=_display_name(prospect.first_name, prospect.last_name, email),
                    email=email,
                    alternate_emails=(),
                    phones=(phone,) if phone else (),
                    status=prospect.status,
                    children=(),
                    schedule=(),
                    locations=(),
                    adult_is_student=False,
                    adult_plans=(),
                    profile_url=f"{base_url}/admin/prospects/{prospect.id}",
                )
            )
    return candidates


def find_shared_phones(candidates: Iterable[ZendeskContactCandidate]) -> dict[str, tuple[str, ...]]:
    owners: dict[str, set[str]] = {}
    for candidate in candidates:
        for phone in candidate.phones:
            owners.setdefault(phone, set()).add(candidate.external_id)
    return {
        phone: tuple(sorted(external_ids))
        for phone, external_ids in owners.items()
        if len(external_ids) > 1
    }


def build_zendesk_user_payload(
    candidate: ZendeskContactCandidate,
    *,
    synced_at: datetime,
    excluded_phones: set[str] | None = None,
) -> dict[str, Any]:
    excluded = excluded_phones or set()
    usable_phones = tuple(phone for phone in candidate.phones if phone not in excluded)
    return {
        "user": {
            "name": candidate.name,
            "email": candidate.email,
            "external_id": candidate.external_id,
            "role": "end-user",
            "phone": usable_phones[0] if usable_phones else None,
            "skip_verify_email": True,
            "tags": ["piano_app_sync", f"piano_{candidate.source_type}"],
            "user_fields": {
                "piano_app_contact_type": "Client / responsable" if candidate.source_type == "client" else "Prospect",
                "piano_app_children": _truncate_field("\n".join(candidate.children), limit=5_000),
                "piano_app_schedule": _truncate_field("\n".join(candidate.schedule), limit=5_000),
                "piano_app_locations": _truncate_field(", ".join(candidate.locations)),
                "piano_app_adult_student": candidate.adult_is_student,
                "piano_app_adult_plans": _truncate_field("\n".join(candidate.adult_plans), limit=5_000),
                "piano_app_profile_url": _truncate_field(candidate.profile_url),
                "piano_app_status": _truncate_field(candidate.status),
                "piano_app_last_sync": synced_at.astimezone(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M"),
            },
        }
    }


class ZendeskClient:
    def __init__(self) -> None:
        if not zendesk_credentials_complete():
            raise RuntimeError("Configuration Zendesk incomplete")
        self._client = httpx.Client(
            base_url=f"https://{settings.zendesk_subdomain.strip()}.zendesk.com/api/v2",
            auth=(f"{settings.zendesk_admin_email.strip()}/token", settings.zendesk_api_token.strip()),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=20.0,
        )

    def __enter__(self) -> ZendeskClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response: httpx.Response | None = None
        for attempt in range(3):
            try:
                response = self._client.request(method, path, **kwargs)
            except httpx.RequestError:
                if attempt >= 2:
                    raise
                time.sleep(1.0)
                continue
            if response.status_code != 429 and response.status_code < 500:
                break
            if attempt < 2:
                retry_after = response.headers.get("Retry-After", "1")
                try:
                    delay = min(max(float(retry_after), 0.25), 10.0)
                except ValueError:
                    delay = 1.0
                time.sleep(delay)
        assert response is not None
        response.raise_for_status()
        if not response.content:
            return {}
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Réponse Zendesk invalide")
        return payload

    def check_connection(self) -> None:
        self._request("GET", "/users/me.json")

    def ensure_user_fields(self) -> None:
        payload = self._request("GET", "/user_fields.json")
        existing = {
            str(field.get("key"))
            for field in payload.get("user_fields", [])
            if isinstance(field, dict) and field.get("key")
        }
        for field in USER_FIELDS:
            if field["key"] in existing:
                continue
            self._request(
                "POST",
                "/user_fields.json",
                json={"user_field": {**field, "active": True}},
            )

    def create_or_update_user(self, payload: dict[str, Any]) -> int:
        response = self._request("POST", "/users/create_or_update.json", json=payload)
        user = response.get("user")
        if not isinstance(user, dict) or not isinstance(user.get("id"), int):
            raise RuntimeError("Zendesk n'a pas renvoyé l'identifiant utilisateur")
        return int(user["id"])

    def ensure_secondary_identities(
        self,
        *,
        user_id: int,
        emails: Iterable[str],
        phones: Iterable[str],
    ) -> None:
        payload = self._request("GET", f"/users/{user_id}/identities.json")
        identities = payload.get("identities", [])
        existing = {
            (str(identity.get("type")), str(identity.get("value", "")).strip().lower())
            for identity in identities
            if isinstance(identity, dict)
        }
        for identity_type, values in (("email", emails), ("phone_number", phones)):
            for value in values:
                normalized_value = value.strip().lower()
                if (identity_type, normalized_value) in existing:
                    continue
                self._request(
                    "POST",
                    f"/users/{user_id}/identities.json",
                    json={
                        "identity": {
                            "type": identity_type,
                            "value": value,
                            "skip_verify_email": True,
                        }
                    },
                )
                existing.add((identity_type, normalized_value))


def run_zendesk_contact_sync_job(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = False,
    full: bool = False,
    check_connection: bool = False,
    triggered_by: str = SOURCE_SCHEDULER,
) -> ZendeskSyncResult:
    ts = now or datetime.now(UTC)
    cursor = get_job_cursor(db, job_name=JOB_NAME)
    since = None if full or cursor is None else cursor.last_processed_at

    with redis_lock(JOB_LOCK_KEY, ttl_seconds=900) as acquired:
        if not acquired:
            raise RuntimeError(f"{JOB_NAME} lock already held")

        job_run = start_job_run(
            db,
            job_name=JOB_NAME,
            job_key="dry_run" if dry_run else "apply",
            triggered_by=triggered_by,
            started_at=ts,
            metadata_json={"limit": limit, "dry_run": dry_run, "full": full, "since": since.isoformat() if since else None},
        )
        checked = processed = synced = skipped = failed = 0
        conflicts = 0
        try:
            candidates = build_zendesk_contact_candidates(db, now=ts, since=since, limit=limit)
            checked = len(candidates)
            shared_phones = find_shared_phones(candidates)
            conflicts = len(shared_phones)
            for phone, owners in shared_phones.items():
                append_job_run_log(
                    db,
                    job_run_id=job_run.id,
                    level="WARNING",
                    message=f"Numéro partagé non synchronisé comme identité : {phone}",
                    context_json={"phone": phone, "contacts": list(owners)},
                )

            if dry_run:
                if check_connection:
                    with ZendeskClient() as zendesk:
                        zendesk.check_connection()
                summary = (
                    f"Contrôle à blanc : {checked} adultes/responsables ou prospects, "
                    f"{conflicts} numéro(s) partagé(s), aucune écriture Zendesk"
                )
            else:
                with ZendeskClient() as zendesk:
                    if check_connection:
                        zendesk.check_connection()
                    zendesk.ensure_user_fields()
                    excluded_phones = set(shared_phones)
                    for candidate in candidates:
                        processed += 1
                        usable_phones = tuple(phone for phone in candidate.phones if phone not in excluded_phones)
                        try:
                            payload = build_zendesk_user_payload(
                                candidate,
                                synced_at=ts,
                                excluded_phones=excluded_phones,
                            )
                            user_id = zendesk.create_or_update_user(payload)
                            zendesk.ensure_secondary_identities(
                                user_id=user_id,
                                emails=candidate.alternate_emails,
                                phones=usable_phones[1:],
                            )
                            synced += 1
                        except (httpx.HTTPError, RuntimeError) as exc:
                            failed += 1
                            append_job_run_log(
                                db,
                                job_run_id=job_run.id,
                                level="ERROR",
                                message=f"Échec synchro Zendesk pour {candidate.external_id}",
                                context_json={"external_id": candidate.external_id, "error": str(exc)},
                            )
                skipped = max(checked - processed, 0)
                upsert_job_cursor(db, job_name=JOB_NAME, last_processed_at=ts, updated_at=ts)
                if full:
                    upsert_job_cursor(db, job_name=FULL_CURSOR_NAME, last_processed_at=ts, updated_at=ts)
                summary = (
                    f"{synced}/{checked} contacts synchronisés vers Zendesk, "
                    f"{failed} échec(s), {conflicts} numéro(s) partagé(s)"
                )

            status = "success"
            if failed:
                status = "warning" if synced else "failed"
            finish_job_run(
                db,
                job_run=job_run,
                status=status,
                finished_at=datetime.now(UTC),
                items_scanned=checked,
                items_processed=processed,
                items_sent=synced,
                items_skipped=skipped,
                items_failed=failed,
                summary_text=summary,
            )
            return ZendeskSyncResult(
                checked=checked,
                processed=processed,
                created_or_updated=synced,
                skipped=skipped,
                failed=failed,
                conflicts=conflicts,
                dry_run=dry_run,
                job_run_id=job_run.id,
            )
        except Exception as exc:
            finish_job_run(
                db,
                job_run=job_run,
                status="failed",
                finished_at=datetime.now(UTC),
                items_scanned=checked,
                items_processed=processed,
                items_sent=synced,
                items_skipped=skipped,
                items_failed=failed + 1,
                error_text=str(exc),
            )
            raise


def zendesk_sync_due(db: Session, *, now: datetime) -> bool:
    cursor = get_job_cursor(db, job_name=JOB_NAME)
    if cursor is None or cursor.last_processed_at is None:
        return False
    interval = timedelta(minutes=max(settings.zendesk_sync_interval_minutes, 5))
    return now - cursor.last_processed_at >= interval


def zendesk_full_sync_due(db: Session, *, now: datetime) -> bool:
    cursor = get_job_cursor(db, job_name=FULL_CURSOR_NAME)
    return cursor is None or cursor.last_processed_at is None or now - cursor.last_processed_at >= timedelta(days=1)
