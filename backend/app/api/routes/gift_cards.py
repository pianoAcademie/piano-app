from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.api.routes.plans import _effective_pack_credits_for_plan, _resolve_plan_owner
from app.models.gift_card import GiftCard, GiftCardEvent
from app.models.plan import ClientPlanSubscription, Plan, PlanKind, SubscriptionStatus
from app.models.user import User, UserRole
from app.schemas.gift_card import (
    AdminGiftCardImportRequest,
    AdminGiftCardOut,
    AdminGiftCardStatusRequest,
    GiftCardCodeRequest,
    GiftCardContextOut,
    GiftCardPublicPreviewOut,
    GiftCardRedeemOut,
    GiftCardRedeemRequest,
)
from app.services.automation_triggers import schedule_plan_purchase_triggers
from app.services.client_status import promote_client_to_active_student
from app.services.gift_cards import (
    decode_gift_card_context,
    encode_gift_card_context,
    gift_card_code_hash,
    gift_card_code_suffix,
    gift_card_external_reference_key,
)
from app.services.legal_terms import resolve_legal_terms
from app.services.notifications.application.orchestrator import enqueue_notifications
from app.services.shared.rate_limit import consume_rate_limit
from app.services.subscriptions import add_months_utc


router = APIRouter()

GIFT_CARD_UNAVAILABLE_DETAIL = "Cette carte cadeau est invalide, inactive ou deja utilisee."


def _request_ip(request: Request) -> str | None:
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    value = forwarded or (request.client.host if request.client is not None else "")
    return value[:64] or None


def _card_can_be_redeemed(card: GiftCard, *, now: datetime) -> bool:
    return bool(
        card.status == "ACTIVE"
        and (card.valid_from is None or card.valid_from <= now)
        and (card.expires_at is None or card.expires_at > now)
        and card.redeemed_at is None
        and card.subscription_id is None
    )


def _unavailable() -> HTTPException:
    # Deliberately use one response for unknown, expired, blocked and already
    # redeemed codes so this public endpoint cannot be used as a code oracle.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=GIFT_CARD_UNAVAILABLE_DETAIL)


def _enforce_lookup_rate_limit(request: Request, *, code_hash: str) -> None:
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    client_ip = forwarded or (request.client.host if request.client is not None else "unknown")
    for bucket, key, limit in (
        ("gift-card-lookup-ip", client_ip, 30),
        ("gift-card-lookup-code", code_hash, 8),
    ):
        allowed, retry_after = consume_rate_limit(bucket=bucket, key=key, limit=limit, window_seconds=3600)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de tentatives. Reessayez plus tard.",
                headers={"Retry-After": str(retry_after)},
            )


def _public_preview(card: GiftCard, plan: Plan) -> GiftCardPublicPreviewOut:
    return GiftCardPublicPreviewOut(
        redeem_token=encode_gift_card_context(card.id),
        status="ACTIVE",
        plan_id=plan.id,
        plan_name=plan.name,
        plan_description=plan.description,
        plan_kind=plan.kind.value,
        recipient_name=card.recipient_name,
        personal_message=card.personal_message,
        expires_at=card.expires_at,
        terms_required=bool(card.terms_required),
    )


def _event(
    card: GiftCard,
    *,
    event_type: str,
    actor_user_id: UUID | None,
    status_before: str | None,
    status_after: str | None,
    metadata: dict[str, object] | None = None,
) -> GiftCardEvent:
    return GiftCardEvent(
        gift_card_id=card.id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        status_before=status_before,
        status_after=status_after,
        metadata_json=metadata or {},
    )


def _admin_out(card: GiftCard, plan: Plan, *, idempotent_replay: bool = False) -> AdminGiftCardOut:
    return AdminGiftCardOut(
        id=card.id,
        code_suffix=card.code_suffix,
        status=card.status,
        source=card.source,
        plan_id=card.plan_id,
        plan_name=plan.name,
        external_order_ref=card.external_order_ref,
        external_line_ref=card.external_line_ref,
        purchaser_name=card.purchaser_name,
        purchaser_email=card.purchaser_email,
        recipient_name=card.recipient_name,
        recipient_email=card.recipient_email,
        face_value_ttc=card.face_value_ttc,
        purchase_price_ttc=card.purchase_price_ttc,
        discount_ttc=card.discount_ttc,
        vat_rate=card.vat_rate,
        currency=card.currency,
        paid_at=card.paid_at,
        valid_from=card.valid_from,
        expires_at=card.expires_at,
        delivered_at=card.delivered_at,
        redeemed_at=card.redeemed_at,
        redeemed_by_user_id=card.redeemed_by_user_id,
        redeemed_for_user_id=card.redeemed_for_user_id,
        subscription_id=card.subscription_id,
        created_at=card.created_at,
        updated_at=card.updated_at,
        idempotent_replay=idempotent_replay,
    )


@router.post("/public/gift-cards/lookup", response_model=GiftCardPublicPreviewOut)
def lookup_gift_card(
    payload: GiftCardCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> GiftCardPublicPreviewOut:
    try:
        code_hash = gift_card_code_hash(payload.code)
    except ValueError as exc:
        raise _unavailable() from exc
    _enforce_lookup_rate_limit(request, code_hash=code_hash)
    card = db.scalar(select(GiftCard).where(GiftCard.code_hash == code_hash).limit(1))
    now = datetime.now(timezone.utc)
    if card is None or not _card_can_be_redeemed(card, now=now):
        raise _unavailable()
    plan = db.scalar(select(Plan).where(Plan.id == card.plan_id, Plan.active.is_(True)))
    if plan is None or plan.kind != PlanKind.PACK:
        raise _unavailable()
    return _public_preview(card, plan)


@router.get("/public/gift-cards/context/{redeem_token}", response_model=GiftCardContextOut)
def gift_card_context(
    redeem_token: str,
    db: Session = Depends(get_db),
) -> GiftCardContextOut:
    card_id = decode_gift_card_context(redeem_token)
    card = db.scalar(select(GiftCard).where(GiftCard.id == card_id).limit(1))
    now = datetime.now(timezone.utc)
    if card is None or not _card_can_be_redeemed(card, now=now):
        raise _unavailable()
    plan = db.scalar(select(Plan).where(Plan.id == card.plan_id, Plan.active.is_(True)))
    if plan is None or plan.kind != PlanKind.PACK:
        raise _unavailable()
    return GiftCardContextOut(**_public_preview(card, plan).model_dump())


@router.post("/gift-cards/redeem", response_model=GiftCardRedeemOut)
def redeem_gift_card(
    payload: GiftCardRedeemRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CLIENT)),
) -> GiftCardRedeemOut:
    card_id = decode_gift_card_context(payload.redeem_token)
    card = db.scalar(select(GiftCard).where(GiftCard.id == card_id).with_for_update())
    now = datetime.now(timezone.utc)
    if card is None or not _card_can_be_redeemed(card, now=now):
        raise _unavailable()

    plan = db.scalar(select(Plan).where(Plan.id == card.plan_id).with_for_update())
    if plan is None or not plan.active or plan.kind != PlanKind.PACK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="L'offre associee a cette carte cadeau n'est plus disponible.",
        )
    owner = _resolve_plan_owner(
        db,
        current_user=current_user,
        requested_user_id=payload.user_id,
    )

    accepted_terms = None
    if card.terms_required or payload.legal_terms_accepted:
        if not payload.legal_terms_accepted:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Vous devez accepter les conditions generales de vente.",
            )
        accepted_terms = resolve_legal_terms(db, payload.legal_terms_language)
        if accepted_terms is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Les conditions generales de vente ne sont pas encore publiees.",
            )

    credits = _effective_pack_credits_for_plan(db, plan=plan) or 0
    ends_at = add_months_utc(now, int(plan.pack_validity_months or 12))
    subscription = ClientPlanSubscription(
        user_id=owner.id,
        payer_contact_id=current_user.id,
        plan_id=plan.id,
        migration_source_code="GIFT_CARD",
        status=SubscriptionStatus.ACTIVE,
        started_at=now,
        ends_at=ends_at,
        credits_initial=credits,
        credits_remaining=credits,
        auto_renew=False,
        bookings_blocked=False,
        billing_method_code="GIFT_CARD",
        last_payment_at=card.paid_at or now,
        last_successful_charge_at=card.paid_at or now,
        last_payment_status="PAID",
        initial_amount_excl_vat=Decimal("0.00"),
        initial_vat_amount=Decimal("0.00"),
        initial_total_incl_vat=Decimal("0.00"),
        initial_currency_code=card.currency,
        initial_price_breakdown_json=[
            {
                "code": "GIFT_CARD_REDEMPTION",
                "label": f"Carte cadeau - {plan.name}",
                "total_incl_vat": "0.00",
            }
        ],
        first_purchase_charges_applied=False,
        legal_terms_accepted_at=now if accepted_terms is not None else None,
        legal_terms_language=accepted_terms.language if accepted_terms is not None else None,
        legal_terms_version=accepted_terms.version if accepted_terms is not None else None,
        legal_terms_content_hash=accepted_terms.content_hash if accepted_terms is not None else None,
        legal_terms_content_snapshot=accepted_terms.content if accepted_terms is not None else None,
        legal_terms_acceptance_ip=_request_ip(request) if accepted_terms is not None else None,
    )
    db.add(subscription)
    db.flush()

    status_before = card.status
    card.status = "REDEEMED"
    card.redeemed_at = now
    card.redeemed_by_user_id = current_user.id
    card.redeemed_for_user_id = owner.id
    card.subscription_id = subscription.id
    card.updated_at = now
    db.add(card)
    db.add(
        _event(
            card,
            event_type="REDEEMED",
            actor_user_id=current_user.id,
            status_before=status_before,
            status_after="REDEEMED",
            metadata={"recipient_user_id": str(owner.id), "subscription_id": str(subscription.id)},
        )
    )
    promote_client_to_active_student(owner)
    db.add(owner)
    automation_notifications = schedule_plan_purchase_triggers(
        db,
        subscription=subscription,
        plan=plan,
        occurred_at=now,
    )
    db.commit()
    enqueue_notifications(automation_notifications)

    return GiftCardRedeemOut(
        gift_card_id=card.id,
        subscription_id=subscription.id,
        redeemed_for_user_id=owner.id,
        plan_id=plan.id,
        plan_name=plan.name,
        credits_granted=credits,
        expires_at=ends_at,
    )


@router.post("/admin/gift-cards/import", response_model=AdminGiftCardOut)
def import_gift_card(
    payload: AdminGiftCardImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminGiftCardOut:
    plan = db.scalar(select(Plan).where(Plan.id == payload.plan_id))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offre introuvable.")
    if plan.kind != PlanKind.PACK:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Une carte cadeau doit etre associee a une formule de type carnet.",
        )
    if payload.expires_at is not None and payload.valid_from is not None and payload.expires_at <= payload.valid_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La date d'expiration doit etre posterieure a la date de debut de validite.",
        )
    try:
        code_hash = gift_card_code_hash(payload.code)
        code_suffix = gift_card_code_suffix(payload.code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le code de carte cadeau est trop court.",
        ) from exc
    external_key = gift_card_external_reference_key(
        source=payload.source,
        external_order_ref=payload.external_order_ref,
        external_line_ref=payload.external_line_ref,
    )

    criteria = [GiftCard.code_hash == code_hash]
    if external_key is not None:
        criteria.append(GiftCard.external_reference_key == external_key)
    existing = db.scalar(select(GiftCard).where(or_(*criteria)).limit(1))
    if existing is not None:
        same_import = bool(
            existing.code_hash == code_hash
            and existing.plan_id == payload.plan_id
            and existing.source == payload.source
            and existing.external_reference_key == external_key
        )
        if not same_import:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ce code ou cette reference externe est deja rattache a une autre carte cadeau.",
            )
        existing_plan = db.scalar(select(Plan).where(Plan.id == existing.plan_id)) or plan
        return _admin_out(existing, existing_plan, idempotent_replay=True)

    now = datetime.now(timezone.utc)
    card = GiftCard(
        code_hash=code_hash,
        code_suffix=code_suffix,
        status=payload.status,
        source=payload.source,
        plan_id=payload.plan_id,
        external_order_ref=payload.external_order_ref,
        external_line_ref=payload.external_line_ref,
        external_reference_key=external_key,
        purchaser_name=payload.purchaser_name,
        purchaser_email=payload.purchaser_email,
        recipient_name=payload.recipient_name,
        recipient_email=payload.recipient_email,
        personal_message=payload.personal_message,
        face_value_ttc=payload.face_value_ttc,
        purchase_price_ttc=payload.purchase_price_ttc,
        discount_ttc=payload.discount_ttc,
        vat_rate=payload.vat_rate,
        currency=payload.currency,
        paid_at=payload.paid_at or (now if payload.status == "ACTIVE" else None),
        valid_from=payload.valid_from,
        expires_at=payload.expires_at,
        delivered_at=payload.delivered_at,
        created_by_user_id=current_user.id,
        terms_required=payload.terms_required,
        metadata_json=payload.metadata,
        created_at=now,
        updated_at=now,
    )
    db.add(card)
    try:
        db.flush()
    except IntegrityError as exc:
        # A second webhook/admin retry may race between the initial lookup and
        # INSERT. Resolve the winner after rollback instead of returning a 500
        # or producing a duplicate card.
        db.rollback()
        existing = db.scalar(select(GiftCard).where(or_(*criteria)).limit(1))
        if existing is not None:
            same_import = bool(
                existing.code_hash == code_hash
                and existing.plan_id == payload.plan_id
                and existing.source == payload.source
                and existing.external_reference_key == external_key
            )
            if same_import:
                existing_plan = db.scalar(select(Plan).where(Plan.id == existing.plan_id))
                if existing_plan is not None:
                    return _admin_out(existing, existing_plan, idempotent_replay=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce code ou cette reference externe est deja utilise.",
        ) from exc
    db.add(
        _event(
            card,
            event_type="IMPORTED",
            actor_user_id=current_user.id,
            status_before=None,
            status_after=card.status,
            metadata={"source": card.source, "external_reference_key": external_key or ""},
        )
    )
    db.commit()
    db.refresh(card)
    return _admin_out(card, plan)


@router.get("/admin/gift-cards", response_model=list[AdminGiftCardOut])
def list_gift_cards(
    search: str | None = Query(default=None, max_length=120),
    card_status: str | None = Query(default=None, alias="status", max_length=20),
    source: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminGiftCardOut]:
    stmt = select(GiftCard, Plan).join(Plan, Plan.id == GiftCard.plan_id)
    if card_status:
        stmt = stmt.where(GiftCard.status == card_status.strip().upper())
    if source:
        stmt = stmt.where(GiftCard.source == source.strip().upper())
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                GiftCard.code_suffix.ilike(pattern),
                GiftCard.external_order_ref.ilike(pattern),
                GiftCard.purchaser_email.ilike(pattern),
                GiftCard.recipient_email.ilike(pattern),
                GiftCard.recipient_name.ilike(pattern),
            )
        )
    rows = db.execute(stmt.order_by(GiftCard.created_at.desc()).limit(limit)).all()
    return [_admin_out(card, plan) for card, plan in rows]


@router.patch("/admin/gift-cards/{gift_card_id}/status", response_model=AdminGiftCardOut)
def update_gift_card_status(
    gift_card_id: UUID,
    payload: AdminGiftCardStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminGiftCardOut:
    card = db.scalar(select(GiftCard).where(GiftCard.id == gift_card_id).with_for_update())
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carte cadeau introuvable.")
    if card.status == "REDEEMED" or card.subscription_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une carte cadeau deja utilisee ne peut plus changer de statut.",
        )
    now = datetime.now(timezone.utc)
    if payload.status == "ACTIVE" and card.expires_at is not None and card.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une carte cadeau expiree ne peut pas etre reactivee.",
        )
    plan = db.scalar(select(Plan).where(Plan.id == card.plan_id))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Offre associee introuvable.")
    if card.status == payload.status:
        return _admin_out(card, plan, idempotent_replay=True)

    previous = card.status
    card.status = payload.status
    card.updated_at = now
    db.add(card)
    db.add(
        _event(
            card,
            event_type="STATUS_CHANGED",
            actor_user_id=current_user.id,
            status_before=previous,
            status_after=payload.status,
        )
    )
    db.commit()
    db.refresh(card)
    return _admin_out(card, plan)
