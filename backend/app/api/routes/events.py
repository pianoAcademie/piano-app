from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_permissions, require_roles
from app.models.catalog import Location
from app.models.event import (
    EVENT_REGISTRATION_CAPACITY_STATUSES,
    SchoolEvent,
    SchoolEventAudience,
    SchoolEventPaymentMode,
    SchoolEventRegistration,
    SchoolEventRegistrationMode,
    SchoolEventRegistrationStatus,
    SchoolEventSlot,
    SchoolEventSlotStatus,
    SchoolEventStatus,
)
from app.models.family import ClientFamilyLink
from app.models.user import ClientKind, User, UserRole
from app.schemas.event import (
    SchoolEventCreateRequest,
    SchoolEventOut,
    SchoolEventRegistrationCreateOut,
    SchoolEventRegistrationCreateRequest,
    SchoolEventRegistrationOut,
    SchoolEventRegistrationStatusUpdateRequest,
    SchoolEventSlotCreateRequest,
    SchoolEventSlotOut,
    SchoolEventUpdateRequest,
    SchoolEventLocationOut,
)
from app.services.client_email import deliverable_client_email
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_frontend_base_url
from app.services.payment_checkout import (
    CheckoutCreateRequest,
    PaymentLookupResult,
    create_checkout_session,
    lookup_payment,
    with_webhook_secret,
)
from app.services.payment_provider import (
    detect_provider_from_reference,
    parse_provider,
    resolve_provider,
    resolve_webhook_secret,
)


router = APIRouter()
ACTIVE_REGISTRATION_STATUSES = {
    SchoolEventRegistrationStatus.PENDING_PAYMENT,
    SchoolEventRegistrationStatus.CONFIRMED,
    SchoolEventRegistrationStatus.WAITLISTED,
    SchoolEventRegistrationStatus.ATTENDED,
    SchoolEventRegistrationStatus.NO_SHOW,
}
PAYMENT_HOLD_DURATION = timedelta(minutes=20)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _display_name(user: User) -> str:
    return f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() or user.email


def _normalized_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if len(slug) < 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Slug invalide")
    return slug[:160]


def _managed_client_ids(db: Session, current_user: User) -> set[UUID]:
    managed = {current_user.id}
    if current_user.client_kind == ClientKind.ADULT:
        managed.update(
            db.scalars(
                select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id == current_user.id)
            ).all()
        )
    return managed


def _capacity_registration_condition(now: datetime):
    return or_(
        SchoolEventRegistration.status.in_(
            [
                SchoolEventRegistrationStatus.CONFIRMED,
                SchoolEventRegistrationStatus.ATTENDED,
                SchoolEventRegistrationStatus.NO_SHOW,
            ]
        ),
        and_(
            SchoolEventRegistration.status == SchoolEventRegistrationStatus.PENDING_PAYMENT,
            or_(
                SchoolEventRegistration.payment_hold_expires_at.is_(None),
                SchoolEventRegistration.payment_hold_expires_at > now,
            ),
        ),
    )


def _location_out(location: Location | None) -> SchoolEventLocationOut | None:
    if location is None:
        return None
    return SchoolEventLocationOut(
        id=location.id,
        name=location.name,
        timezone=location.timezone,
        is_online=bool(location.is_online),
    )


def _registration_counts(db: Session, slot_ids: list[UUID]) -> tuple[dict[UUID, int], dict[UUID, int]]:
    booked: dict[UUID, int] = defaultdict(int)
    waitlisted: dict[UUID, int] = defaultdict(int)
    if not slot_ids:
        return booked, waitlisted
    rows = db.execute(
        select(
            SchoolEventRegistration.slot_id,
            SchoolEventRegistration.status,
            func.coalesce(func.sum(SchoolEventRegistration.party_size), 0),
        )
        .where(
            SchoolEventRegistration.slot_id.in_(slot_ids),
            or_(
                SchoolEventRegistration.status != SchoolEventRegistrationStatus.PENDING_PAYMENT,
                SchoolEventRegistration.payment_hold_expires_at.is_(None),
                SchoolEventRegistration.payment_hold_expires_at > _utcnow(),
            ),
        )
        .group_by(SchoolEventRegistration.slot_id, SchoolEventRegistration.status)
    ).all()
    for slot_id, registration_status, count in rows:
        if registration_status in EVENT_REGISTRATION_CAPACITY_STATUSES:
            booked[slot_id] += int(count or 0)
        elif registration_status == SchoolEventRegistrationStatus.WAITLISTED:
            waitlisted[slot_id] += int(count or 0)
    return booked, waitlisted


def _serialize_events(db: Session, events: list[SchoolEvent]) -> list[SchoolEventOut]:
    event_ids = [event.id for event in events]
    slots = db.scalars(
        select(SchoolEventSlot)
        .where(SchoolEventSlot.event_id.in_(event_ids))
        .order_by(SchoolEventSlot.start_at_utc.asc())
    ).all() if event_ids else []
    location_ids = {
        location_id
        for location_id in [*(event.location_id for event in events), *(slot.location_id for slot in slots)]
        if location_id is not None
    }
    locations = db.scalars(select(Location).where(Location.id.in_(location_ids))).all() if location_ids else []
    locations_by_id = {location.id: location for location in locations}
    slots_by_event: dict[UUID, list[SchoolEventSlot]] = defaultdict(list)
    for slot in slots:
        slots_by_event[slot.event_id].append(slot)
    booked_by_slot, waitlisted_by_slot = _registration_counts(db, [slot.id for slot in slots])
    payload: list[SchoolEventOut] = []
    for event in events:
        event_slots: list[SchoolEventSlotOut] = []
        for slot in slots_by_event.get(event.id, []):
            booked = booked_by_slot.get(slot.id, 0)
            event_slots.append(
                SchoolEventSlotOut(
                    id=slot.id,
                    event_id=event.id,
                    label=slot.label,
                    start_at_utc=slot.start_at_utc,
                    end_at_utc=slot.end_at_utc,
                    timezone=slot.timezone,
                    capacity_max=slot.capacity_max,
                    booked_count=booked,
                    seats_remaining=max(slot.capacity_max - booked, 0),
                    waitlist_count=waitlisted_by_slot.get(slot.id, 0),
                    status=slot.status,
                    location=_location_out(locations_by_id.get(slot.location_id or event.location_id)),
                )
            )
        payload.append(
            SchoolEventOut(
                id=event.id,
                slug=event.slug,
                title_fr=event.title_fr,
                title_en=event.title_en,
                description_fr=event.description_fr,
                description_en=event.description_en,
                category=event.category,
                image_url=event.image_url,
                status=event.status,
                audience=event.audience,
                registration_mode=event.registration_mode,
                payment_mode=event.payment_mode,
                location=_location_out(locations_by_id.get(event.location_id)),
                booking_opens_at=event.booking_opens_at,
                booking_closes_at=event.booking_closes_at,
                price_ttc=event.price_ttc,
                currency=event.currency,
                max_per_family=event.max_per_family,
                waitlist_enabled=bool(event.waitlist_enabled),
                cancellation_deadline_hours=event.cancellation_deadline_hours,
                collect_piece_info=bool(event.collect_piece_info),
                collect_photo_consent=bool(event.collect_photo_consent),
                confirmation_message_fr=event.confirmation_message_fr,
                confirmation_message_en=event.confirmation_message_en,
                slots=event_slots,
                registration_count=sum(slot.booked_count for slot in event_slots),
                waitlist_count=sum(slot.waitlist_count for slot in event_slots),
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
        )
    return payload


def _registration_out(
    registration: SchoolEventRegistration,
    *,
    event: SchoolEvent,
    slot: SchoolEventSlot,
    location: Location | None,
) -> SchoolEventRegistrationOut:
    return SchoolEventRegistrationOut(
        id=registration.id,
        group_id=registration.group_id,
        event_id=event.id,
        event_slug=event.slug,
        event_title_fr=event.title_fr,
        event_title_en=event.title_en,
        slot_id=slot.id,
        slot_label=slot.label,
        start_at_utc=slot.start_at_utc,
        end_at_utc=slot.end_at_utc,
        timezone=slot.timezone,
        location_name=location.name if location else None,
        booker_user_id=registration.booker_user_id,
        participant_user_id=registration.participant_user_id,
        participant_display_name=registration.participant_display_name,
        party_size=registration.party_size,
        guest_names=list(registration.guest_names_json or []),
        answers=dict(registration.answers_json or {}),
        status=registration.status,
        unit_price_ttc_snapshot=registration.unit_price_ttc_snapshot,
        total_ttc_snapshot=registration.total_ttc_snapshot,
        currency_snapshot=registration.currency_snapshot,
        payment_provider=registration.payment_provider,
        payment_reference=registration.payment_reference,
        payment_hold_expires_at=registration.payment_hold_expires_at,
        booked_at=registration.booked_at,
        cancelled_at=registration.cancelled_at,
        checked_in_at=registration.checked_in_at,
    )


def _event_is_open(event: SchoolEvent, now: datetime) -> bool:
    if event.status != SchoolEventStatus.PUBLISHED:
        return False
    if event.booking_opens_at and now < event.booking_opens_at:
        return False
    if event.booking_closes_at and now >= event.booking_closes_at:
        return False
    return True


def _send_registration_confirmation(
    *,
    booker: User,
    event: SchoolEvent,
    slot: SchoolEventSlot,
    status_value: SchoolEventRegistrationStatus,
    participant_names: list[str],
) -> None:
    email = deliverable_client_email(booker)
    if not email:
        return
    language = (booker.preferred_language or "fr").strip().lower()
    is_english = language.startswith("en")
    title = event.title_en if is_english and event.title_en else event.title_fr
    try:
        slot_timezone = ZoneInfo(slot.timezone)
    except (KeyError, ValueError):
        slot_timezone = timezone.utc
    when = slot.start_at_utc.astimezone(slot_timezone).strftime("%d/%m/%Y %H:%M")
    waiting = status_value == SchoolEventRegistrationStatus.WAITLISTED
    subject = (
        f"Waiting list - {title}" if is_english and waiting
        else f"Registration confirmed - {title}" if is_english
        else f"Liste d'attente - {title}" if waiting
        else f"Inscription confirmée - {title}"
    )
    custom_message = event.confirmation_message_en if is_english else event.confirmation_message_fr
    body = (
        f"Your registration for {title} is {'on the waiting list' if waiting else 'confirmed'}.\n"
        f"Date: {when}\nParticipants: {', '.join(participant_names)}"
        if is_english
        else f"Votre inscription à {title} est {'sur liste d’attente' if waiting else 'confirmée'}.\n"
        f"Date : {when}\nParticipants : {', '.join(participant_names)}"
    )
    if custom_message and custom_message.strip():
        body = f"{body}\n\n{custom_message.strip()}"
    send_email(
        to_email=email,
        subject=subject,
        body=body,
        context="SCHOOL_EVENT_REGISTRATION",
        recipient_user_id=booker.id,
        communication_type="EVENT_REGISTRATION",
    )


def _send_payment_required(
    *,
    db: Session,
    booker: User,
    event: SchoolEvent,
    slot: SchoolEventSlot,
    participant_names: list[str],
) -> None:
    email = deliverable_client_email(booker)
    if not email:
        return
    language = (booker.preferred_language or "fr").strip().lower()
    is_english = language.startswith("en")
    title = event.title_en if is_english and event.title_en else event.title_fr
    try:
        slot_timezone = ZoneInfo(slot.timezone)
    except (KeyError, ValueError):
        slot_timezone = timezone.utc
    when = slot.start_at_utc.astimezone(slot_timezone).strftime("%d/%m/%Y %H:%M")
    base_url = resolve_frontend_base_url(db).rstrip("/")
    payment_url = f"{base_url}/events/{event.slug}"
    subject = f"Payment required - {title}" if is_english else f"Paiement requis - {title}"
    body = (
        f"A place is available for {title}.\n"
        f"Date: {when}\nParticipants: {', '.join(participant_names)}\n\n"
        f"Complete payment within 20 minutes: {payment_url}"
        if is_english
        else f"Une place est disponible pour {title}.\n"
        f"Date : {when}\nParticipants : {', '.join(participant_names)}\n\n"
        f"Finalisez le paiement sous 20 minutes : {payment_url}"
    )
    send_email(
        to_email=email,
        subject=subject,
        body=body,
        context="SCHOOL_EVENT_PAYMENT_REQUIRED",
        recipient_user_id=booker.id,
        communication_type="EVENT_PAYMENT_REQUIRED",
    )


def _event_checkout_urls(db: Session, *, event: SchoolEvent, group_id: UUID) -> tuple[str, str, str]:
    base_url = resolve_frontend_base_url(db).rstrip("/")
    event_path = f"/events/{event.slug}"
    success_url = f"{base_url}{event_path}?payment_return=success&payment_group={group_id}"
    cancel_url = f"{base_url}{event_path}?payment_return=cancel&payment_group={group_id}"
    webhook_url = with_webhook_secret(
        f"{base_url}/api/v1/public/payments/webhook",
        resolve_webhook_secret(db),
    )
    return success_url, cancel_url, webhook_url


def _create_event_checkout(
    db: Session,
    *,
    event: SchoolEvent,
    slot: SchoolEventSlot,
    booker: User,
    rows: list[SchoolEventRegistration],
) -> str:
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inscription introuvable")
    group_id = rows[0].group_id
    total_due = sum((Decimal(row.total_ttc_snapshot or 0) for row in rows), Decimal("0.00")).quantize(Decimal("0.01"))
    if total_due <= Decimal("0.00"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Aucun paiement n’est requis")
    success_url, cancel_url, webhook_url = _event_checkout_urls(db, event=event, group_id=group_id)
    checkout = create_checkout_session(
        db,
        CheckoutCreateRequest(
            amount=total_due,
            currency=(event.currency or "EUR").upper(),
            description=f"{event.title_fr} ({len(rows)} inscription(s))",
            customer_email=deliverable_client_email(booker) or booker.email,
            customer_first_name=booker.first_name,
            customer_last_name=booker.last_name,
            customer_country=(booker.residence_country or "FR"),
            success_return_url=success_url,
            cancel_return_url=cancel_url,
            webhook_url=webhook_url,
            metadata={
                "source": "SCHOOL_EVENT",
                "event_registration_group_id": str(group_id),
                "event_id": str(event.id),
                "event_slot_id": str(slot.id),
                "client_id": str(booker.id),
            },
        ),
    )
    if not checkout.success or not checkout.checkout_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Impossible de créer la session de paiement ({checkout.message})",
        )
    hold_expires_at = _utcnow() + PAYMENT_HOLD_DURATION
    for row in rows:
        row.status = SchoolEventRegistrationStatus.PENDING_PAYMENT
        row.payment_provider = checkout.provider.value
        row.payment_reference = checkout.provider_reference
        row.payment_checkout_url = checkout.checkout_url
        row.payment_hold_expires_at = hold_expires_at
    db.commit()
    return checkout.checkout_url


def reconcile_event_payment_by_provider_reference(
    db: Session,
    *,
    group_id: UUID,
    payment_reference: str,
    preloaded_lookup: PaymentLookupResult | None = None,
) -> dict[str, object]:
    joined = db.execute(
        select(SchoolEventRegistration, SchoolEventSlot, SchoolEvent)
        .join(SchoolEventSlot, SchoolEventSlot.id == SchoolEventRegistration.slot_id)
        .join(SchoolEvent, SchoolEvent.id == SchoolEventSlot.event_id)
        .where(SchoolEventRegistration.group_id == group_id)
        .with_for_update()
    ).all()
    if not joined:
        return {"ok": True, "processed": False, "reason": "event_registration_not_found"}
    rows = [item[0] for item in joined]
    slot = joined[0][1]
    event = joined[0][2]
    stored_references = {row.payment_reference for row in rows if row.payment_reference}
    if stored_references and payment_reference not in stored_references:
        return {"ok": True, "processed": False, "reason": "reference_mismatch"}
    provider = (
        preloaded_lookup.provider
        if preloaded_lookup is not None
        else detect_provider_from_reference(payment_reference)
        or parse_provider(rows[0].payment_provider)
        or resolve_provider(db)
    )
    lookup = preloaded_lookup or lookup_payment(db, provider=provider, payment_reference=payment_reference)
    if lookup.metadata.get("event_registration_group_id") not in {None, "", str(group_id)}:
        return {"ok": True, "processed": False, "reason": "event_group_mismatch"}
    was_pending = any(row.status == SchoolEventRegistrationStatus.PENDING_PAYMENT for row in rows)
    promoted_groups: list[list[SchoolEventRegistration]] = []
    if lookup.paid:
        for row in rows:
            if row.status == SchoolEventRegistrationStatus.PENDING_PAYMENT:
                row.status = SchoolEventRegistrationStatus.CONFIRMED
            row.payment_provider = lookup.provider.value
            row.payment_reference = lookup.provider_reference or payment_reference
            row.payment_checkout_url = None
            row.payment_hold_expires_at = None
        db.commit()
        if was_pending:
            booker = db.get(User, rows[0].booker_user_id)
            if booker is not None:
                _send_registration_confirmation(
                    booker=booker,
                    event=event,
                    slot=slot,
                    status_value=SchoolEventRegistrationStatus.CONFIRMED,
                    participant_names=[row.participant_display_name for row in rows],
                )
    elif lookup.success and (lookup.cancelled or lookup.failed):
        released_capacity = any(row.status == SchoolEventRegistrationStatus.PENDING_PAYMENT for row in rows)
        for row in rows:
            if row.status == SchoolEventRegistrationStatus.PENDING_PAYMENT:
                row.status = SchoolEventRegistrationStatus.CANCELLED
                row.cancelled_at = _utcnow()
                row.cancellation_reason = "PAYMENT_CANCELLED" if lookup.cancelled else "PAYMENT_FAILED"
            row.payment_hold_expires_at = None
            row.payment_checkout_url = None
        db.flush()
        promoted_groups = _promote_waitlist(db, slot) if released_capacity else []
        db.commit()
        _send_waitlist_promotions(db, event=event, slot=slot, promoted_groups=promoted_groups)
    return {
        "ok": True,
        "processed": bool(lookup.paid or (lookup.success and (lookup.cancelled or lookup.failed))),
        "payment_status": (lookup.status or "UNKNOWN").strip().upper(),
        "registration_status": rows[0].status.value,
    }


@router.get("/events", response_model=list[SchoolEventOut])
def list_public_events(
    category: str | None = None,
    db: Session = Depends(get_db),
) -> list[SchoolEventOut]:
    stmt = select(SchoolEvent).where(
        SchoolEvent.status == SchoolEventStatus.PUBLISHED,
        SchoolEvent.audience == SchoolEventAudience.PUBLIC,
    )
    if category:
        stmt = stmt.where(func.upper(SchoolEvent.category) == category.strip().upper())
    events = db.scalars(stmt.order_by(SchoolEvent.created_at.desc())).all()
    return _serialize_events(db, list(events))


@router.get("/events/{slug}", response_model=SchoolEventOut)
def get_public_event(slug: str, db: Session = Depends(get_db)) -> SchoolEventOut:
    event = db.scalar(
        select(SchoolEvent).where(
            SchoolEvent.slug == slug,
            SchoolEvent.status == SchoolEventStatus.PUBLISHED,
            SchoolEvent.audience == SchoolEventAudience.PUBLIC,
        )
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Événement introuvable")
    return _serialize_events(db, [event])[0]


@router.get("/clients/me/events", response_model=list[SchoolEventOut])
def list_client_events(
    category: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[SchoolEventOut]:
    stmt = select(SchoolEvent).where(SchoolEvent.status == SchoolEventStatus.PUBLISHED)
    if category:
        stmt = stmt.where(func.upper(SchoolEvent.category) == category.strip().upper())
    events = db.scalars(stmt.order_by(SchoolEvent.created_at.desc())).all()
    return _serialize_events(db, list(events))


@router.get("/clients/me/event-registrations", response_model=list[SchoolEventRegistrationOut])
def list_my_event_registrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> list[SchoolEventRegistrationOut]:
    managed_ids = _managed_client_ids(db, current_user)
    rows = db.execute(
        select(SchoolEventRegistration, SchoolEventSlot, SchoolEvent, Location)
        .join(SchoolEventSlot, SchoolEventSlot.id == SchoolEventRegistration.slot_id)
        .join(SchoolEvent, SchoolEvent.id == SchoolEventSlot.event_id)
        .outerjoin(Location, Location.id == func.coalesce(SchoolEventSlot.location_id, SchoolEvent.location_id))
        .where(
            (SchoolEventRegistration.booker_user_id == current_user.id)
            | (SchoolEventRegistration.participant_user_id.in_(managed_ids))
        )
        .order_by(SchoolEventSlot.start_at_utc.desc(), SchoolEventRegistration.booked_at.desc())
    ).all()
    return [_registration_out(registration, event=event, slot=slot, location=location) for registration, slot, event, location in rows]


@router.post("/clients/me/events/{slug}/register", response_model=SchoolEventRegistrationCreateOut)
def register_for_event(
    slug: str,
    payload: SchoolEventRegistrationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> SchoolEventRegistrationCreateOut:
    now = _utcnow()
    event = db.scalar(select(SchoolEvent).where(SchoolEvent.slug == slug).with_for_update())
    if event is None or not _event_is_open(event, now):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Les inscriptions ne sont pas ouvertes")
    slot = db.scalar(
        select(SchoolEventSlot)
        .where(SchoolEventSlot.id == payload.slot_id, SchoolEventSlot.event_id == event.id)
        .with_for_update()
    )
    if slot is None or slot.status != SchoolEventSlotStatus.SCHEDULED or slot.start_at_utc <= now:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce créneau n’est plus disponible")
    managed_ids = _managed_client_ids(db, current_user)
    participant_ids = list(dict.fromkeys(payload.participant_user_ids))
    if any(participant_id not in managed_ids for participant_id in participant_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Participant non autorisé")
    guests = [name.strip() for name in payload.guest_names if name.strip()]
    total_people = len(participant_ids) + len(guests)
    if total_people < 1:
        participant_ids = [current_user.id]
        total_people = 1
    if total_people > event.max_per_family:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nombre maximal de participants dépassé")
    if event.registration_mode == SchoolEventRegistrationMode.INDIVIDUAL_SLOT and total_people != 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ce créneau accepte un seul participant")

    users = db.scalars(select(User).where(User.id.in_(participant_ids))).all() if participant_ids else []
    users_by_id = {user.id: user for user in users}
    if len(users_by_id) != len(participant_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Participant introuvable")
    existing_participants = set(
        db.scalars(
            select(SchoolEventRegistration.participant_user_id).where(
                SchoolEventRegistration.slot_id == slot.id,
                SchoolEventRegistration.participant_user_id.in_(participant_ids),
                SchoolEventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                or_(
                    SchoolEventRegistration.status != SchoolEventRegistrationStatus.PENDING_PAYMENT,
                    SchoolEventRegistration.payment_hold_expires_at.is_(None),
                    SchoolEventRegistration.payment_hold_expires_at > now,
                ),
            )
        ).all()
    ) if participant_ids else set()
    if existing_participants:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un participant est déjà inscrit sur ce créneau")

    booked_count = int(
        db.scalar(
            select(func.coalesce(func.sum(SchoolEventRegistration.party_size), 0)).where(
                SchoolEventRegistration.slot_id == slot.id,
                _capacity_registration_condition(now),
            )
        )
        or 0
    )
    seats_remaining = max(slot.capacity_max - booked_count, 0)
    registration_status = SchoolEventRegistrationStatus.CONFIRMED
    if total_people > seats_remaining:
        if not event.waitlist_enabled:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce créneau est complet")
        registration_status = SchoolEventRegistrationStatus.WAITLISTED
    elif event.payment_mode == SchoolEventPaymentMode.ONLINE and Decimal(event.price_ttc or 0) > Decimal("0"):
        registration_status = SchoolEventRegistrationStatus.PENDING_PAYMENT

    group_id = uuid4()
    answers: dict[str, object] = {}
    if event.collect_piece_info:
        answers["piece_info"] = (payload.piece_info or "").strip()
    if event.collect_photo_consent:
        answers["photo_consent"] = bool(payload.photo_consent)
    rows_to_create: list[SchoolEventRegistration] = []
    unit_price = Decimal(event.price_ttc or 0).quantize(Decimal("0.01"))
    for participant_id in participant_ids:
        participant = users_by_id[participant_id]
        rows_to_create.append(
            SchoolEventRegistration(
                group_id=group_id,
                slot_id=slot.id,
                booker_user_id=current_user.id,
                participant_user_id=participant.id,
                participant_display_name=_display_name(participant),
                party_size=1,
                guest_names_json=[],
                answers_json=answers,
                status=registration_status,
                unit_price_ttc_snapshot=unit_price,
                total_ttc_snapshot=unit_price,
                currency_snapshot=event.currency.upper(),
                payment_hold_expires_at=(
                    now + PAYMENT_HOLD_DURATION
                    if registration_status == SchoolEventRegistrationStatus.PENDING_PAYMENT
                    else None
                ),
            )
        )
    if guests:
        rows_to_create.append(
            SchoolEventRegistration(
                group_id=group_id,
                slot_id=slot.id,
                booker_user_id=current_user.id,
                participant_user_id=None,
                participant_display_name=", ".join(guests),
                party_size=len(guests),
                guest_names_json=guests,
                answers_json=answers,
                status=registration_status,
                unit_price_ttc_snapshot=unit_price,
                total_ttc_snapshot=(unit_price * len(guests)).quantize(Decimal("0.01")),
                currency_snapshot=event.currency.upper(),
                payment_hold_expires_at=(
                    now + PAYMENT_HOLD_DURATION
                    if registration_status == SchoolEventRegistrationStatus.PENDING_PAYMENT
                    else None
                ),
            )
        )
    db.add_all(rows_to_create)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Une inscription existe déjà") from exc
    for row in rows_to_create:
        db.refresh(row)
    location = db.get(Location, slot.location_id or event.location_id) if (slot.location_id or event.location_id) else None
    checkout_url: str | None = None
    if registration_status == SchoolEventRegistrationStatus.PENDING_PAYMENT:
        checkout_url = _create_event_checkout(
            db,
            event=event,
            slot=slot,
            booker=current_user,
            rows=rows_to_create,
        )
    else:
        _send_registration_confirmation(
            booker=current_user,
            event=event,
            slot=slot,
            status_value=registration_status,
            participant_names=[row.participant_display_name for row in rows_to_create],
        )
    return SchoolEventRegistrationCreateOut(
        group_id=group_id,
        status=registration_status,
        registrations=[_registration_out(row, event=event, slot=slot, location=location) for row in rows_to_create],
        checkout_url=checkout_url,
    )


def _promote_waitlist(db: Session, slot: SchoolEventSlot) -> list[list[SchoolEventRegistration]]:
    now = _utcnow()
    booked_count = int(
        db.scalar(
            select(func.coalesce(func.sum(SchoolEventRegistration.party_size), 0)).where(
                SchoolEventRegistration.slot_id == slot.id,
                _capacity_registration_condition(now),
            )
        )
        or 0
    )
    remaining = max(slot.capacity_max - booked_count, 0)
    if remaining <= 0:
        return []
    waitlisted = db.scalars(
        select(SchoolEventRegistration)
        .where(
            SchoolEventRegistration.slot_id == slot.id,
            SchoolEventRegistration.status == SchoolEventRegistrationStatus.WAITLISTED,
        )
        .order_by(SchoolEventRegistration.booked_at.asc())
        .with_for_update()
    ).all()
    groups: dict[UUID, list[SchoolEventRegistration]] = defaultdict(list)
    for row in waitlisted:
        groups[row.group_id].append(row)
    event = db.get(SchoolEvent, slot.event_id)
    payment_required = bool(
        event
        and event.payment_mode == SchoolEventPaymentMode.ONLINE
        and Decimal(event.price_ttc or 0) > Decimal("0")
    )
    promoted: list[list[SchoolEventRegistration]] = []
    for rows in groups.values():
        group_size = sum(row.party_size for row in rows)
        if group_size > remaining:
            continue
        for row in rows:
            row.status = (
                SchoolEventRegistrationStatus.PENDING_PAYMENT
                if payment_required
                else SchoolEventRegistrationStatus.CONFIRMED
            )
            row.payment_hold_expires_at = now + PAYMENT_HOLD_DURATION if payment_required else None
        promoted.append(rows)
        remaining -= group_size
        if remaining <= 0:
            break
    return promoted


def _send_waitlist_promotions(
    db: Session,
    *,
    event: SchoolEvent,
    slot: SchoolEventSlot,
    promoted_groups: list[list[SchoolEventRegistration]],
) -> None:
    for rows in promoted_groups:
        if not rows:
            continue
        booker = db.get(User, rows[0].booker_user_id)
        if booker is None:
            continue
        if rows[0].status == SchoolEventRegistrationStatus.PENDING_PAYMENT:
            _send_payment_required(
                db=db,
                booker=booker,
                event=event,
                slot=slot,
                participant_names=[row.participant_display_name for row in rows],
            )
        else:
            _send_registration_confirmation(
                booker=booker,
                event=event,
                slot=slot,
                status_value=SchoolEventRegistrationStatus.CONFIRMED,
                participant_names=[row.participant_display_name for row in rows],
            )


@router.post(
    "/clients/me/event-registrations/{group_id}/checkout",
    response_model=SchoolEventRegistrationCreateOut,
)
def checkout_event_registration_group(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> SchoolEventRegistrationCreateOut:
    now = _utcnow()
    rows = db.scalars(
        select(SchoolEventRegistration)
        .where(
            SchoolEventRegistration.group_id == group_id,
            SchoolEventRegistration.booker_user_id == current_user.id,
            SchoolEventRegistration.status == SchoolEventRegistrationStatus.PENDING_PAYMENT,
        )
        .with_for_update()
    ).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paiement d’inscription introuvable")
    slot = db.scalar(
        select(SchoolEventSlot)
        .where(SchoolEventSlot.id == rows[0].slot_id)
        .with_for_update()
    )
    event = db.get(SchoolEvent, slot.event_id) if slot else None
    if slot is None or event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Événement introuvable")
    if (
        event.payment_mode != SchoolEventPaymentMode.ONLINE
        or Decimal(event.price_ttc or 0) <= Decimal("0")
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Aucun paiement en ligne n’est requis")
    if slot.status != SchoolEventSlotStatus.SCHEDULED or slot.start_at_utc <= now:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce créneau n’est plus disponible")

    active_checkout_urls = {
        (row.payment_checkout_url or "").strip()
        for row in rows
        if row.payment_checkout_url
        and row.payment_hold_expires_at
        and row.payment_hold_expires_at > now
    }
    if len(active_checkout_urls) == 1:
        checkout_url = next(iter(active_checkout_urls))
        location = db.get(Location, slot.location_id or event.location_id) if (slot.location_id or event.location_id) else None
        return SchoolEventRegistrationCreateOut(
            group_id=group_id,
            status=SchoolEventRegistrationStatus.PENDING_PAYMENT,
            registrations=[_registration_out(row, event=event, slot=slot, location=location) for row in rows],
            checkout_url=checkout_url,
        )

    group_size = sum(row.party_size for row in rows)
    booked_elsewhere = int(
        db.scalar(
            select(func.coalesce(func.sum(SchoolEventRegistration.party_size), 0)).where(
                SchoolEventRegistration.slot_id == slot.id,
                SchoolEventRegistration.group_id != group_id,
                _capacity_registration_condition(now),
            )
        )
        or 0
    )
    if booked_elsewhere + group_size > slot.capacity_max:
        for row in rows:
            row.status = SchoolEventRegistrationStatus.WAITLISTED
            row.payment_hold_expires_at = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La place n’est plus disponible. Votre inscription a été replacée sur liste d’attente.",
        )
    hold_expires_at = now + PAYMENT_HOLD_DURATION
    for row in rows:
        row.payment_hold_expires_at = hold_expires_at
    db.flush()
    checkout_url = _create_event_checkout(
        db,
        event=event,
        slot=slot,
        booker=current_user,
        rows=list(rows),
    )
    location = db.get(Location, slot.location_id or event.location_id) if (slot.location_id or event.location_id) else None
    return SchoolEventRegistrationCreateOut(
        group_id=group_id,
        status=SchoolEventRegistrationStatus.PENDING_PAYMENT,
        registrations=[_registration_out(row, event=event, slot=slot, location=location) for row in rows],
        checkout_url=checkout_url,
    )


@router.post("/clients/me/event-registrations/{group_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_event_registration_group(
    group_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> Response:
    rows = db.scalars(
        select(SchoolEventRegistration)
        .where(
            SchoolEventRegistration.group_id == group_id,
            SchoolEventRegistration.booker_user_id == current_user.id,
            SchoolEventRegistration.status.in_(
                [
                    SchoolEventRegistrationStatus.PENDING_PAYMENT,
                    SchoolEventRegistrationStatus.CONFIRMED,
                    SchoolEventRegistrationStatus.WAITLISTED,
                ]
            ),
        )
        .with_for_update()
    ).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inscription introuvable")
    slot = db.scalar(select(SchoolEventSlot).where(SchoolEventSlot.id == rows[0].slot_id).with_for_update())
    event = db.get(SchoolEvent, slot.event_id) if slot else None
    now = _utcnow()
    if slot is None or event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Événement introuvable")
    if slot.start_at_utc < now + timedelta(hours=event.cancellation_deadline_hours):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La date limite d’annulation est dépassée")
    had_capacity = any(
        row.status in {
            SchoolEventRegistrationStatus.PENDING_PAYMENT,
            SchoolEventRegistrationStatus.CONFIRMED,
        }
        for row in rows
    )
    for row in rows:
        row.status = SchoolEventRegistrationStatus.CANCELLED
        row.cancelled_at = now
        row.cancellation_reason = "CLIENT_CANCELLED"
        row.payment_checkout_url = None
        row.payment_hold_expires_at = None
    db.flush()
    promoted_groups = _promote_waitlist(db, slot) if had_capacity else []
    db.commit()
    _send_waitlist_promotions(db, event=event, slot=slot, promoted_groups=promoted_groups)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/events", response_model=list[SchoolEventOut])
def list_admin_events(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_events")),
) -> list[SchoolEventOut]:
    events = db.scalars(select(SchoolEvent).order_by(SchoolEvent.created_at.desc())).all()
    return _serialize_events(db, list(events))


@router.post("/admin/events", response_model=SchoolEventOut, status_code=status.HTTP_201_CREATED)
def create_admin_event(
    payload: SchoolEventCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_permissions("can_manage_events")),
) -> SchoolEventOut:
    event = SchoolEvent(
        **payload.model_dump(exclude={"slug", "category", "currency"}),
        slug=_normalized_slug(payload.slug),
        category=payload.category.strip().upper(),
        currency=payload.currency.strip().upper(),
        created_by_user_id=current_user.id,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce slug est déjà utilisé") from exc
    db.refresh(event)
    return _serialize_events(db, [event])[0]


@router.get("/admin/events/{event_id}", response_model=SchoolEventOut)
def get_admin_event(
    event_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_events")),
) -> SchoolEventOut:
    event = db.get(SchoolEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Événement introuvable")
    return _serialize_events(db, [event])[0]


@router.put("/admin/events/{event_id}", response_model=SchoolEventOut)
def update_admin_event(
    event_id: UUID,
    payload: SchoolEventUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_events")),
) -> SchoolEventOut:
    event = db.get(SchoolEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Événement introuvable")
    values = payload.model_dump(exclude={"slug"})
    for key, value in values.items():
        setattr(event, key, value)
    event.slug = _normalized_slug(payload.slug)
    event.category = payload.category.strip().upper()
    event.currency = payload.currency.strip().upper()
    event.updated_at = _utcnow()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce slug est déjà utilisé") from exc
    db.refresh(event)
    return _serialize_events(db, [event])[0]


@router.post("/admin/events/{event_id}/slots", response_model=SchoolEventSlotOut, status_code=status.HTTP_201_CREATED)
def create_admin_event_slot(
    event_id: UUID,
    payload: SchoolEventSlotCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_events")),
) -> SchoolEventSlotOut:
    event = db.get(SchoolEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Événement introuvable")
    slot = SchoolEventSlot(event_id=event.id, **payload.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    serialized_slots = _serialize_events(db, [event])[0].slots
    return next(serialized_slot for serialized_slot in serialized_slots if serialized_slot.id == slot.id)


@router.delete("/admin/events/{event_id}/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_event_slot(
    event_id: UUID,
    slot_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_events")),
) -> Response:
    slot = db.scalar(select(SchoolEventSlot).where(SchoolEventSlot.id == slot_id, SchoolEventSlot.event_id == event_id))
    if slot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Créneau introuvable")
    active_count = int(
        db.scalar(
            select(func.count(SchoolEventRegistration.id)).where(
                SchoolEventRegistration.slot_id == slot.id,
                SchoolEventRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )
        or 0
    )
    if active_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Impossible de supprimer un créneau avec des inscrits")
    db.delete(slot)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/events/{event_id}/registrations", response_model=list[SchoolEventRegistrationOut])
def list_admin_event_registrations(
    event_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_events")),
) -> list[SchoolEventRegistrationOut]:
    rows = db.execute(
        select(SchoolEventRegistration, SchoolEventSlot, SchoolEvent, Location)
        .join(SchoolEventSlot, SchoolEventSlot.id == SchoolEventRegistration.slot_id)
        .join(SchoolEvent, SchoolEvent.id == SchoolEventSlot.event_id)
        .outerjoin(Location, Location.id == func.coalesce(SchoolEventSlot.location_id, SchoolEvent.location_id))
        .where(SchoolEvent.id == event_id)
        .order_by(SchoolEventSlot.start_at_utc.asc(), SchoolEventRegistration.booked_at.asc())
    ).all()
    return [_registration_out(registration, event=event, slot=slot, location=location) for registration, slot, event, location in rows]


@router.patch("/admin/event-registrations/{registration_id}/status", response_model=SchoolEventRegistrationOut)
def update_admin_event_registration_status(
    registration_id: UUID,
    payload: SchoolEventRegistrationStatusUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_permissions("can_manage_events")),
) -> SchoolEventRegistrationOut:
    row = db.execute(
        select(SchoolEventRegistration, SchoolEventSlot, SchoolEvent, Location)
        .join(SchoolEventSlot, SchoolEventSlot.id == SchoolEventRegistration.slot_id)
        .join(SchoolEvent, SchoolEvent.id == SchoolEventSlot.event_id)
        .outerjoin(Location, Location.id == func.coalesce(SchoolEventSlot.location_id, SchoolEvent.location_id))
        .where(SchoolEventRegistration.id == registration_id)
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inscription introuvable")
    registration, slot, event, location = row
    registration.status = payload.status
    registration.checked_in_at = _utcnow() if payload.status == SchoolEventRegistrationStatus.ATTENDED else None
    if payload.status != SchoolEventRegistrationStatus.PENDING_PAYMENT:
        registration.payment_checkout_url = None
        registration.payment_hold_expires_at = None
    promoted_groups: list[list[SchoolEventRegistration]] = []
    if payload.status == SchoolEventRegistrationStatus.CANCELLED:
        registration.cancelled_at = _utcnow()
        registration.cancellation_reason = "ADMIN_CANCELLED"
        db.flush()
        promoted_groups = _promote_waitlist(db, slot)
    db.commit()
    db.refresh(registration)
    _send_waitlist_promotions(db, event=event, slot=slot, promoted_groups=promoted_groups)
    return _registration_out(registration, event=event, slot=slot, location=location)
