from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import io
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.core.config import settings
from app.models.catalog import CourseType
from app.models.product_catalog import CatalogKit, CatalogProduct
from app.models.quote import (
    CgvVersion,
    PaymentPlan,
    PricingActivityPrice,
    PricingCatalog,
    PricingKitPrice,
    PricingProductPrice,
    Prospect,
    Quote,
    QuoteAcceptanceFollowup,
    QuoteEmailOutbox,
    QuoteEvent,
    QuoteLine,
    QuoteType,
    SolfegeLevelRule,
)
from app.models.user import ClientStatus, User, UserRole
from app.schemas.quote import (
    CgvVersionOut,
    CgvVersionUpsertRequest,
    PaymentPlanOut,
    PaymentPlanUpsertRequest,
    PricingActivityPriceOut,
    PricingActivityPriceUpsertRequest,
    PricingCatalogOut,
    PricingCatalogUpsertRequest,
    PricingKitPriceOut,
    PricingKitPriceUpsertRequest,
    PricingProductPriceOut,
    PricingProductPriceUpsertRequest,
    ProspectCreateRequest,
    ProspectOut,
    ProspectUpdateRequest,
    QuoteCalendarPreviewRequest,
    QuoteChangeRequestIn,
    QuoteCreateRequest,
    QuoteDetailOut,
    QuoteFollowupOut,
    QuoteFollowupPaymentMethodRequest,
    QuoteFollowupSlotRequest,
    QuoteFollowupUpdateRequest,
    QuoteLineIn,
    QuoteLineOut,
    QuoteOut,
    QuotePaymentSchedulePreviewRequest,
    QuotePublicOut,
    QuoteSendRequest,
    QuoteTypeOut,
    QuoteTypeUpsertRequest,
    QuoteUpdateRequest,
    SolfegeLevelRuleOut,
    SolfegeLevelRuleUpsertRequest,
)
from app.services.email_delivery import send_email
from app.services.quotes.calendar_engine import CalendarGenerationInput, generate_calendar_snapshot
from app.services.quotes.lifecycle_jobs import run_quote_daily_lifecycle_job
from app.services.quotes.payment_plan_engine import PaymentPlanScheduleInput, build_payment_schedule
from app.services.quotes.quote_documents import render_quote_pdf
from app.services.security import hash_password

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _q2(value: Decimal) -> Decimal:
    return Decimal(value or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _new_quote_number() -> str:
    return f"DV-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2).upper()}"


def _time_from_hhmm(value: str, *, field: str) -> time:
    raw = (value or "").strip()
    try:
        hour_s, minute_s = raw.split(":", 1)
        hour = int(hour_s)
        minute = int(minute_s)
        return time(hour=hour, minute=minute)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field} must be HH:MM") from exc


def _prospect_out(row: Prospect) -> ProspectOut:
    return ProspectOut(
        id=row.id,
        linked_client_id=row.linked_client_id,
        status=row.status,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
        phone=row.phone,
        source=row.source,
        notes=row.notes,
        meta=row.meta or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _line_out(row: QuoteLine) -> QuoteLineOut:
    return QuoteLineOut(
        id=row.id,
        quote_id=row.quote_id,
        line_category=row.line_category,
        line_type=row.line_type,
        master_item_type=row.master_item_type,
        master_item_id=row.master_item_id,
        activity_id=row.activity_id,
        product_id=row.product_id,
        kit_id=row.kit_id,
        code=row.code,
        title=row.title,
        description=row.description,
        duration_minutes=row.duration_minutes,
        pricing_unit=row.pricing_unit,
        quantity=_q2(Decimal(row.quantity or 0)),
        unit_price_ttc=_q2(Decimal(row.unit_price_ttc or 0)),
        amount_ttc=_q2(Decimal(row.amount_ttc or 0)),
        sort_order=int(row.sort_order or 0),
        meta=row.meta or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _quote_out(row: Quote) -> QuoteOut:
    return QuoteOut(
        id=row.id,
        quote_number=row.quote_number,
        context_type=row.context_type,
        quote_type=row.quote_type,
        quote_type_id=row.quote_type_id,
        pricing_catalog_id=row.pricing_catalog_id,
        prospect_id=row.prospect_id,
        client_id=row.client_id,
        location_id=row.location_id,
        payment_plan_id=row.payment_plan_id,
        status=row.status,
        public_token=row.public_token,
        pdf_token=row.pdf_token,
        version_number=int(row.version_number or 1),
        parent_quote_id=row.parent_quote_id,
        currency=row.currency,
        total_ttc=_q2(Decimal(row.total_ttc or 0)),
        expiry_days=int(row.expiry_days or 10),
        expires_at=row.expires_at,
        sent_at=row.sent_at,
        approved_at=row.approved_at,
        rejected_at=row.rejected_at,
        expired_at=row.expired_at,
        cancelled_at=row.cancelled_at,
        school_year_label=row.school_year_label,
        estimated_solfege_level=row.estimated_solfege_level,
        solfege_duration_minutes=row.solfege_duration_minutes,
        selected_solfege_slot=row.selected_solfege_slot or {},
        calendar_snapshot=row.calendar_snapshot or {},
        payment_terms_snapshot=row.payment_terms_snapshot or {},
        cgv_snapshot=row.cgv_snapshot or {},
        price_snapshot=row.price_snapshot or {},
        meta=row.meta or {},
        reminder_sent_at=row.reminder_sent_at,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _payment_plan_out(row: PaymentPlan) -> PaymentPlanOut:
    return PaymentPlanOut(
        id=row.id,
        code=row.code,
        name=row.name,
        payment_method=row.payment_method,
        schedule_type=row.schedule_type,
        schedule_rules=row.schedule_rules or {},
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _cgv_out(row: CgvVersion) -> CgvVersionOut:
    return CgvVersionOut(
        id=row.id,
        version_label=row.version_label,
        content=row.content,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _quote_type_out(row: QuoteType) -> QuoteTypeOut:
    return QuoteTypeOut(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        default_expiry_days=int(row.default_expiry_days or 10),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pricing_catalog_out(row: PricingCatalog) -> PricingCatalogOut:
    return PricingCatalogOut(
        id=row.id,
        name=row.name,
        school_year_label=row.school_year_label,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        is_default=bool(row.is_default),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pricing_activity_price_out(row: PricingActivityPrice) -> PricingActivityPriceOut:
    return PricingActivityPriceOut(
        id=row.id,
        catalog_id=row.catalog_id,
        activity_id=row.activity_id,
        location_id=row.location_id,
        student_category=row.student_category,
        pricing_unit=row.pricing_unit,
        unit_price_ttc=_q2(Decimal(row.unit_price_ttc or 0)),
        currency=row.currency,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pricing_product_price_out(row: PricingProductPrice) -> PricingProductPriceOut:
    return PricingProductPriceOut(
        id=row.id,
        catalog_id=row.catalog_id,
        product_id=row.product_id,
        unit_price_ttc=_q2(Decimal(row.unit_price_ttc or 0)),
        currency=row.currency,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pricing_kit_price_out(row: PricingKitPrice) -> PricingKitPriceOut:
    return PricingKitPriceOut(
        id=row.id,
        catalog_id=row.catalog_id,
        kit_id=row.kit_id,
        unit_price_ttc=_q2(Decimal(row.unit_price_ttc or 0)),
        currency=row.currency,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _solfege_rule_out(row: SolfegeLevelRule) -> SolfegeLevelRuleOut:
    return SolfegeLevelRuleOut(
        id=row.id,
        level_code=row.level_code,
        duration_minutes=int(row.duration_minutes),
        allowed_weekdays=[int(v) for v in (row.allowed_weekdays or [])],
        allowed_time_slots=list(row.allowed_time_slots or []),
        location_id=row.location_id,
        modality=row.modality,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _followup_out(row: QuoteAcceptanceFollowup) -> QuoteFollowupOut:
    return QuoteFollowupOut(
        id=row.id,
        quote_id=row.quote_id,
        target_client_id=row.target_client_id,
        status=row.status,
        payment_method_status=row.payment_method_status,
        solfege_slot_status=row.solfege_slot_status,
        payload=row.payload or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _load_quote(db: Session, quote_id: UUID, *, lock: bool = False) -> Quote:
    stmt = select(Quote).where(Quote.id == quote_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return row


def _load_quote_lines(db: Session, quote_id: UUID) -> list[QuoteLine]:
    return db.scalars(
        select(QuoteLine)
        .where(QuoteLine.quote_id == quote_id)
        .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
    ).all()


def _quote_detail_out(db: Session, quote: Quote) -> QuoteDetailOut:
    lines = _load_quote_lines(db, quote.id)
    return QuoteDetailOut(quote=_quote_out(quote), lines=[_line_out(row) for row in lines])


def _resolve_recipient_email(db: Session, quote: Quote, explicit_email: str | None = None) -> str | None:
    if explicit_email and explicit_email.strip():
        return explicit_email.strip().lower()
    from_meta = str((quote.meta or {}).get("recipient_email") or "").strip().lower()
    if from_meta:
        return from_meta
    if quote.prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))
        if prospect is not None and prospect.email:
            return prospect.email.strip().lower()
    if quote.client_id is not None:
        user = db.scalar(select(User).where(User.id == quote.client_id))
        if user is not None and user.email:
            return user.email.strip().lower()
    return None


def _build_payment_schedule_for_quote(db: Session, quote: Quote, *, total_ttc: Decimal) -> list[dict[str, object]]:
    if quote.payment_plan_id is None:
        return []
    plan = db.scalar(select(PaymentPlan).where(PaymentPlan.id == quote.payment_plan_id))
    if plan is None:
        return []
    registration_date = _utcnow().date()
    return build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code=plan.payment_method,
            total_ttc=total_ttc,
            registration_date=registration_date,
            currency=(quote.currency or "EUR").upper(),
        )
    )


def _effective_item_price(
    db: Session,
    *,
    line: QuoteLineIn,
    pricing_catalog_id: UUID | None,
) -> tuple[str | None, str, str | None, int | None, Decimal, dict[str, object]]:
    title = line.title
    code = line.code
    description = line.description
    duration = line.duration_minutes
    unit_price = _q2(line.unit_price_ttc)
    meta = dict(line.meta)

    if line.activity_id is not None:
        activity = db.scalar(select(CourseType).where(CourseType.id == line.activity_id, CourseType.active.is_(True)))
        if activity is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown activity_id")
        code = activity.code
        title = activity.name
        description = activity.description
        duration = int(activity.duration_minutes)
        if pricing_catalog_id is not None:
            activity_price = db.scalar(
                select(PricingActivityPrice)
                .where(
                    PricingActivityPrice.catalog_id == pricing_catalog_id,
                    PricingActivityPrice.activity_id == line.activity_id,
                    PricingActivityPrice.is_active.is_(True),
                )
                .order_by(PricingActivityPrice.location_id.asc().nullsfirst())
                .limit(1)
            )
            if activity_price is not None:
                unit_price = _q2(Decimal(activity_price.unit_price_ttc))
                meta["pricing_source"] = "catalog_activity"
        if unit_price <= Decimal("0") and activity.default_course_rate_ttc is not None:
            unit_price = _q2(Decimal(activity.default_course_rate_ttc))
            meta["pricing_source"] = "activity_default_course_rate"

    if line.product_id is not None:
        product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == line.product_id, CatalogProduct.active.is_(True)))
        if product is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown product_id")
        code = code or product.barcode
        title = product.title
        description = line.description or product.short_description or product.long_description
        if pricing_catalog_id is not None:
            product_price = db.scalar(
                select(PricingProductPrice)
                .where(
                    PricingProductPrice.catalog_id == pricing_catalog_id,
                    PricingProductPrice.product_id == line.product_id,
                    PricingProductPrice.is_active.is_(True),
                )
                .limit(1)
            )
            if product_price is not None:
                unit_price = _q2(Decimal(product_price.unit_price_ttc))
                meta["pricing_source"] = "catalog_product"
        if unit_price <= Decimal("0"):
            unit_price = _q2(Decimal(product.price_incl_vat or 0))
            meta["pricing_source"] = "product_price_incl_vat"

    if line.kit_id is not None:
        kit = db.scalar(select(CatalogKit).where(CatalogKit.id == line.kit_id, CatalogKit.active.is_(True)))
        if kit is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown kit_id")
        code = code or kit.code
        title = kit.title
        description = line.description or kit.short_description or kit.long_description
        if pricing_catalog_id is not None:
            kit_price = db.scalar(
                select(PricingKitPrice)
                .where(
                    PricingKitPrice.catalog_id == pricing_catalog_id,
                    PricingKitPrice.kit_id == line.kit_id,
                    PricingKitPrice.is_active.is_(True),
                )
                .limit(1)
            )
            if kit_price is not None:
                unit_price = _q2(Decimal(kit_price.unit_price_ttc))
                meta["pricing_source"] = "catalog_kit"
        if unit_price <= Decimal("0"):
            if (kit.price_mode or "").strip().lower() == "forced" and kit.forced_price is not None:
                unit_price = _q2(Decimal(kit.forced_price))
            else:
                unit_price = _q2(Decimal(kit.price_incl_vat or 0))
            meta["pricing_source"] = "kit_price"

    return code, title, description, duration, unit_price, meta


def _materialize_quote_lines(
    db: Session,
    *,
    quote: Quote,
    lines_in: list[QuoteLineIn],
) -> Decimal:
    db.query(QuoteLine).filter(QuoteLine.quote_id == quote.id).delete(synchronize_session=False)
    total = Decimal("0.00")

    for item in lines_in:
        if item.line_category == "service" and item.line_type == "item" and item.activity_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service line requires activity_id")
        if item.line_category == "product" and item.line_type == "item" and item.product_id is None and item.kit_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Product line requires product_id or kit_id")

        code, title, description, duration, unit_price, meta = _effective_item_price(
            db,
            line=item,
            pricing_catalog_id=quote.pricing_catalog_id,
        )

        quantity = _q2(item.quantity)
        amount = _q2(quantity * unit_price)
        if item.line_type == "discount":
            amount = _q2(-abs(amount))
            unit_price = _q2(-abs(unit_price))
        elif item.line_type == "surcharge":
            amount = _q2(abs(amount))
            unit_price = _q2(abs(unit_price))

        row = QuoteLine(
            quote_id=quote.id,
            line_category=item.line_category,
            line_type=item.line_type,
            master_item_type=item.master_item_type,
            master_item_id=item.master_item_id,
            activity_id=item.activity_id,
            product_id=item.product_id,
            kit_id=item.kit_id,
            code=code,
            title=title,
            description=description,
            duration_minutes=duration,
            pricing_unit=item.pricing_unit,
            quantity=quantity,
            unit_price_ttc=unit_price,
            amount_ttc=amount,
            sort_order=int(item.sort_order),
            meta=meta,
        )
        db.add(row)
        total += amount

    quote.total_ttc = _q2(total)
    quote.updated_at = _utcnow()
    db.add(quote)
    db.flush()
    return _q2(total)


def _ensure_quote_editable(quote: Quote) -> None:
    if quote.status != "created":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote is immutable once sent")


def _ensure_public_token(quote: Quote) -> None:
    if not quote.public_token:
        quote.public_token = _new_token()
    if not quote.pdf_token:
        quote.pdf_token = _new_token()


@router.get("/prospects", response_model=list[ProspectOut])
def list_prospects(
    q: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[ProspectOut]:
    stmt = select(Prospect)
    if status_filter:
        stmt = stmt.where(Prospect.status == status_filter.strip())
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Prospect.email.ilike(pattern),
                Prospect.first_name.ilike(pattern),
                Prospect.last_name.ilike(pattern),
                Prospect.phone.ilike(pattern),
            )
        )
    rows = db.scalars(stmt.order_by(Prospect.created_at.desc()).limit(limit)).all()
    return [_prospect_out(row) for row in rows]


@router.post("/prospects", response_model=ProspectOut, status_code=status.HTTP_201_CREATED)
def create_prospect(
    payload: ProspectCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProspectOut:
    email = payload.email.strip().lower()
    existing = db.scalar(select(Prospect).where(Prospect.email == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Prospect already exists")

    now = _utcnow()
    row = Prospect(
        linked_client_id=payload.linked_client_id,
        status="active",
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=email,
        phone=payload.phone,
        source=payload.source,
        notes=payload.notes,
        meta=payload.meta,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _prospect_out(row)


@router.get("/prospects/{prospect_id}", response_model=ProspectOut)
def get_prospect(
    prospect_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProspectOut:
    row = db.scalar(select(Prospect).where(Prospect.id == prospect_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return _prospect_out(row)


@router.patch("/prospects/{prospect_id}", response_model=ProspectOut)
def update_prospect(
    prospect_id: UUID,
    payload: ProspectUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProspectOut:
    row = db.scalar(select(Prospect).where(Prospect.id == prospect_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")

    if payload.linked_client_id is not None:
        row.linked_client_id = payload.linked_client_id
    if payload.status is not None:
        row.status = payload.status.strip()
    if payload.first_name is not None:
        row.first_name = payload.first_name
    if payload.last_name is not None:
        row.last_name = payload.last_name
    if payload.email is not None:
        email = payload.email.strip().lower()
        duplicate = db.scalar(select(Prospect.id).where(Prospect.email == email, Prospect.id != row.id).limit(1))
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Prospect email already used")
        row.email = email
    if payload.phone is not None:
        row.phone = payload.phone
    if payload.source is not None:
        row.source = payload.source
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.meta is not None:
        row.meta = payload.meta
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _prospect_out(row)


@router.post("/prospects/from-client/{client_id}", response_model=ProspectOut)
def create_prospect_from_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProspectOut:
    user = db.scalar(select(User).where(User.id == client_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    existing = db.scalar(select(Prospect).where(Prospect.linked_client_id == client_id).limit(1))
    if existing is not None:
        return _prospect_out(existing)

    existing_by_email = db.scalar(select(Prospect).where(Prospect.email == user.email).limit(1))
    if existing_by_email is not None:
        existing_by_email.linked_client_id = client_id
        existing_by_email.updated_at = _utcnow()
        db.add(existing_by_email)
        db.commit()
        db.refresh(existing_by_email)
        return _prospect_out(existing_by_email)

    now = _utcnow()
    row = Prospect(
        linked_client_id=client_id,
        status="active",
        first_name=user.first_name,
        last_name=user.last_name,
        email=(user.email or "").strip().lower(),
        phone=user.mobile_phone_1 or user.phone,
        source="from_client",
        meta={"origin": "client"},
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _prospect_out(row)


@router.get("/quotes", response_model=list[QuoteOut])
def list_quotes(
    status_filter: str | None = Query(default=None, alias="status"),
    context_type: str | None = None,
    prospect_id: UUID | None = None,
    client_id: UUID | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteOut]:
    stmt = select(Quote)
    if status_filter:
        stmt = stmt.where(Quote.status == status_filter.strip())
    if context_type:
        stmt = stmt.where(Quote.context_type == context_type.strip())
    if prospect_id is not None:
        stmt = stmt.where(Quote.prospect_id == prospect_id)
    if client_id is not None:
        stmt = stmt.where(Quote.client_id == client_id)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(Quote.quote_number.ilike(pattern))

    rows = db.scalars(stmt.order_by(Quote.created_at.desc()).limit(limit)).all()
    return [_quote_out(row) for row in rows]


@router.post("/quotes/calendar/preview")
def preview_quote_calendar(
    payload: QuoteCalendarPreviewRequest,
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    snapshot = generate_calendar_snapshot(
        CalendarGenerationInput(
            start_date=payload.start_date,
            end_date=payload.end_date,
            weekdays=payload.weekdays,
            start_time=_time_from_hhmm(payload.start_time, field="start_time"),
            end_time=_time_from_hhmm(payload.end_time, field="end_time"),
            activity_id=payload.activity_id,
            location_id=payload.location_id,
            modality=payload.modality,
            holiday_dates=payload.holiday_dates,
            closure_dates=payload.closure_dates,
        )
    )
    return snapshot


@router.post("/quotes/payment-schedule/preview")
def preview_quote_payment_schedule(
    payload: QuotePaymentSchedulePreviewRequest,
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    schedule = build_payment_schedule(
        PaymentPlanScheduleInput(
            payment_method_code=payload.payment_method_code,
            total_ttc=payload.total_ttc,
            registration_date=payload.registration_date,
            currency=payload.currency.upper(),
        )
    )
    return {"schedule": schedule}


@router.post("/quotes", response_model=QuoteDetailOut, status_code=status.HTTP_201_CREATED)
def create_quote(
    payload: QuoteCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    if payload.context_type == "acquisition" and payload.prospect_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="prospect_id is required for acquisition quote")
    if payload.context_type == "active_client" and payload.client_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="client_id is required for active_client quote")

    if payload.prospect_id is not None:
        prospect = db.scalar(select(Prospect).where(Prospect.id == payload.prospect_id))
        if prospect is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    if payload.client_id is not None:
        client = db.scalar(select(User).where(User.id == payload.client_id))
        if client is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    now = _utcnow()
    quote_dt = datetime.combine(payload.quote_date or now.date(), time(0, 0), tzinfo=timezone.utc)
    expires_at = quote_dt + timedelta(days=int(payload.expiry_days))

    row = Quote(
        quote_number=_new_quote_number(),
        context_type=payload.context_type,
        quote_type=payload.quote_type,
        quote_type_id=payload.quote_type_id,
        pricing_catalog_id=payload.pricing_catalog_id,
        prospect_id=payload.prospect_id,
        client_id=payload.client_id,
        location_id=payload.location_id,
        payment_plan_id=payload.payment_plan_id,
        status="created",
        version_number=1,
        currency=payload.currency.upper(),
        total_ttc=Decimal("0"),
        expiry_days=int(payload.expiry_days),
        expires_at=expires_at,
        school_year_label=payload.school_year_label,
        estimated_solfege_level=payload.estimated_solfege_level,
        selected_solfege_slot=payload.selected_solfege_slot,
        calendar_snapshot=payload.calendar_snapshot,
        payment_terms_snapshot=payload.payment_terms_snapshot,
        cgv_snapshot=payload.cgv_snapshot,
        price_snapshot=payload.price_snapshot,
        meta=payload.meta,
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )

    if row.estimated_solfege_level:
        solfege_rule = db.scalar(
            select(SolfegeLevelRule)
            .where(
                SolfegeLevelRule.level_code == row.estimated_solfege_level,
                SolfegeLevelRule.is_active.is_(True),
            )
            .order_by(SolfegeLevelRule.created_at.desc())
            .limit(1)
        )
        if solfege_rule is not None:
            row.solfege_duration_minutes = int(solfege_rule.duration_minutes)

    if not row.cgv_snapshot:
        cgv = db.scalar(select(CgvVersion).where(CgvVersion.is_active.is_(True)).order_by(CgvVersion.created_at.desc()).limit(1))
        if cgv is not None:
            row.cgv_snapshot = {"version_label": cgv.version_label, "content": cgv.content}

    db.add(row)
    db.flush()

    total = _materialize_quote_lines(db, quote=row, lines_in=payload.lines)
    if not row.payment_terms_snapshot:
        row.payment_terms_snapshot = {
            "schedule": _build_payment_schedule_for_quote(db, row, total_ttc=total),
            "currency": row.currency,
        }
    if not row.price_snapshot:
        row.price_snapshot = {
            "catalog_id": str(row.pricing_catalog_id) if row.pricing_catalog_id else None,
            "currency": row.currency,
            "total_ttc": str(total),
        }

    db.add(
        QuoteEvent(
            quote_id=row.id,
            event_type="quote_created",
            actor_type="admin",
            actor_id=current_user.id,
            payload={"context_type": row.context_type},
        )
    )
    db.commit()
    db.refresh(row)
    return _quote_detail_out(db, row)


@router.get("/quotes/{quote_id}", response_model=QuoteDetailOut)
def get_quote(
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    row = _load_quote(db, quote_id)
    return _quote_detail_out(db, row)


@router.patch("/quotes/{quote_id}", response_model=QuoteDetailOut)
def update_quote(
    quote_id: UUID,
    payload: QuoteUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    row = _load_quote(db, quote_id, lock=True)
    _ensure_quote_editable(row)

    if payload.quote_type is not None:
        row.quote_type = payload.quote_type
    if payload.quote_type_id is not None:
        row.quote_type_id = payload.quote_type_id
    if payload.pricing_catalog_id is not None:
        row.pricing_catalog_id = payload.pricing_catalog_id
    if payload.location_id is not None:
        row.location_id = payload.location_id
    if payload.payment_plan_id is not None:
        row.payment_plan_id = payload.payment_plan_id
    if payload.school_year_label is not None:
        row.school_year_label = payload.school_year_label
    if payload.currency is not None:
        row.currency = payload.currency.upper()
    if payload.expiry_days is not None:
        row.expiry_days = int(payload.expiry_days)
        row.expires_at = _utcnow() + timedelta(days=int(payload.expiry_days))
    if payload.estimated_solfege_level is not None:
        row.estimated_solfege_level = payload.estimated_solfege_level
    if payload.selected_solfege_slot is not None:
        row.selected_solfege_slot = payload.selected_solfege_slot
    if payload.calendar_snapshot is not None:
        row.calendar_snapshot = payload.calendar_snapshot
    if payload.payment_terms_snapshot is not None:
        row.payment_terms_snapshot = payload.payment_terms_snapshot
    if payload.cgv_snapshot is not None:
        row.cgv_snapshot = payload.cgv_snapshot
    if payload.price_snapshot is not None:
        row.price_snapshot = payload.price_snapshot
    if payload.meta is not None:
        row.meta = payload.meta

    if payload.lines is not None:
        total = _materialize_quote_lines(db, quote=row, lines_in=payload.lines)
        if payload.payment_terms_snapshot is None:
            row.payment_terms_snapshot = {
                "schedule": _build_payment_schedule_for_quote(db, row, total_ttc=total),
                "currency": row.currency,
            }

    row.updated_at = _utcnow()
    db.add(row)
    db.add(
        QuoteEvent(
            quote_id=row.id,
            event_type="quote_updated",
            actor_type="admin",
            actor_id=current_user.id,
            payload={},
        )
    )
    db.commit()
    db.refresh(row)
    return _quote_detail_out(db, row)


@router.post("/quotes/{quote_id}/duplicate", response_model=QuoteDetailOut, status_code=status.HTTP_201_CREATED)
def duplicate_quote(
    quote_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    source = _load_quote(db, quote_id)
    lines = _load_quote_lines(db, quote_id)
    now = _utcnow()

    clone = Quote(
        quote_number=_new_quote_number(),
        context_type=source.context_type,
        quote_type=source.quote_type,
        quote_type_id=source.quote_type_id,
        pricing_catalog_id=source.pricing_catalog_id,
        prospect_id=source.prospect_id,
        client_id=source.client_id,
        location_id=source.location_id,
        payment_plan_id=source.payment_plan_id,
        status="created",
        version_number=int(source.version_number or 1) + 1,
        parent_quote_id=source.id,
        currency=source.currency,
        total_ttc=source.total_ttc,
        expiry_days=source.expiry_days,
        expires_at=now + timedelta(days=int(source.expiry_days or 10)),
        school_year_label=source.school_year_label,
        estimated_solfege_level=source.estimated_solfege_level,
        solfege_duration_minutes=source.solfege_duration_minutes,
        selected_solfege_slot=source.selected_solfege_slot,
        calendar_snapshot=source.calendar_snapshot,
        payment_terms_snapshot=source.payment_terms_snapshot,
        cgv_snapshot=source.cgv_snapshot,
        price_snapshot=source.price_snapshot,
        meta={**(source.meta or {}), "duplicated_from": str(source.id)},
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(clone)
    db.flush()

    for line in lines:
        db.add(
            QuoteLine(
                quote_id=clone.id,
                line_category=line.line_category,
                line_type=line.line_type,
                master_item_type=line.master_item_type,
                master_item_id=line.master_item_id,
                activity_id=line.activity_id,
                product_id=line.product_id,
                kit_id=line.kit_id,
                code=line.code,
                title=line.title,
                description=line.description,
                duration_minutes=line.duration_minutes,
                pricing_unit=line.pricing_unit,
                quantity=line.quantity,
                unit_price_ttc=line.unit_price_ttc,
                amount_ttc=line.amount_ttc,
                sort_order=line.sort_order,
                meta=line.meta,
                created_at=now,
                updated_at=now,
            )
        )

    db.add(
        QuoteEvent(
            quote_id=clone.id,
            event_type="quote_duplicated",
            actor_type="admin",
            actor_id=current_user.id,
            payload={"source_quote_id": str(source.id)},
        )
    )
    db.commit()
    db.refresh(clone)
    return _quote_detail_out(db, clone)


@router.post("/quotes/{quote_id}/generate-pdf")
def generate_quote_pdf(
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> StreamingResponse:
    quote = _load_quote(db, quote_id)
    lines = _load_quote_lines(db, quote_id)
    pdf_bytes = render_quote_pdf(quote=quote, lines=lines)
    filename = f"devis-{quote.quote_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/quotes/{quote_id}/pdf")
def download_quote_pdf(
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> StreamingResponse:
    quote = _load_quote(db, quote_id)
    lines = _load_quote_lines(db, quote_id)
    pdf_bytes = render_quote_pdf(quote=quote, lines=lines)
    filename = f"devis-{quote.quote_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _send_quote_email(
    db: Session,
    *,
    quote: Quote,
    recipient_email: str,
    kind: str,
    actor_id: UUID | None,
) -> None:
    now = _utcnow()
    message_key = f"{kind}:{quote.id}:{recipient_email}"
    existing = db.scalar(select(QuoteEmailOutbox).where(QuoteEmailOutbox.message_key == message_key).limit(1))
    if existing is not None:
        return

    frontend_base = (settings.frontend_base_url or "http://localhost:3000").rstrip("/")
    public_url = f"{frontend_base}/q/{quote.id}?t={quote.public_token}"
    pdf_url = f"{frontend_base}/api/v1/public/quotes/{quote.id}/pdf?t={quote.pdf_token}"
    subject = f"Devis {quote.quote_number}"
    body = (
        f"Votre devis {quote.quote_number} est disponible.\n\n"
        f"Consulter et agir: {public_url}\n"
        f"Telecharger le PDF: {pdf_url}\n"
        f"Total TTC: {quote.total_ttc} {quote.currency}\n"
    )

    out = QuoteEmailOutbox(
        quote_id=quote.id,
        kind=kind,
        message_key=message_key,
        recipient_email=recipient_email,
        subject=subject,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(out)
    db.flush()

    provider_message_id = send_email(
        to_email=recipient_email,
        subject=subject,
        body=body,
        body_format="TEXT",
        context="QUOTE_SENT",
    )
    out.provider_message_id = provider_message_id
    out.status = "sent" if provider_message_id else "failed"
    out.sent_at = now if provider_message_id else None
    out.updated_at = now
    db.add(out)

    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_email_sent",
            actor_type="admin",
            actor_id=actor_id,
            payload={"kind": kind, "recipient_email": recipient_email},
            created_at=now,
        )
    )


@router.post("/quotes/{quote_id}/send", response_model=QuoteDetailOut)
def send_quote(
    quote_id: UUID,
    payload: QuoteSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    quote = _load_quote(db, quote_id, lock=True)
    _ensure_quote_editable(quote)
    _ensure_public_token(quote)

    now = _utcnow()
    quote.status = "sent"
    quote.sent_at = now
    if quote.expires_at is None:
        quote.expires_at = now + timedelta(days=int(quote.expiry_days or 10))
    quote.updated_at = now

    recipient = _resolve_recipient_email(db, quote, explicit_email=payload.recipient_email)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No recipient email resolved for quote")

    quote.meta = {**(quote.meta or {}), "recipient_email": recipient}
    db.add(quote)
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_sent",
            actor_type="admin",
            actor_id=current_user.id,
            payload={"recipient_email": recipient},
            created_at=now,
        )
    )
    _send_quote_email(db, quote=quote, recipient_email=recipient, kind="quote_sent", actor_id=current_user.id)
    db.commit()
    db.refresh(quote)
    return _quote_detail_out(db, quote)


@router.post("/quotes/{quote_id}/resend", response_model=QuoteDetailOut)
def resend_quote(
    quote_id: UUID,
    payload: QuoteSendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteDetailOut:
    quote = _load_quote(db, quote_id, lock=True)
    if quote.status not in {"sent", "approved", "rejected", "expired"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote cannot be resent in current status")
    _ensure_public_token(quote)

    recipient = _resolve_recipient_email(db, quote, explicit_email=payload.recipient_email)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No recipient email resolved for quote")

    quote.meta = {**(quote.meta or {}), "recipient_email": recipient}
    quote.updated_at = _utcnow()
    db.add(quote)
    _send_quote_email(db, quote=quote, recipient_email=recipient, kind="quote_resend", actor_id=current_user.id)
    db.commit()
    db.refresh(quote)
    return _quote_detail_out(db, quote)


@router.get("/public/quotes/{quote_id}", response_model=QuotePublicOut)
def public_get_quote(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> QuotePublicOut:
    quote = _load_quote(db, quote_id)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    lines = _load_quote_lines(db, quote.id)
    payment_schedule = list((quote.payment_terms_snapshot or {}).get("schedule", []))
    return QuotePublicOut(
        quote=_quote_out(quote),
        lines=[_line_out(row) for row in lines],
        payment_schedule=payment_schedule,
    )


def _ensure_followup(db: Session, quote: Quote) -> QuoteAcceptanceFollowup:
    followup = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == quote.id).limit(1))
    if followup is not None:
        return followup
    now = _utcnow()
    followup = QuoteAcceptanceFollowup(
        quote_id=quote.id,
        target_client_id=quote.client_id,
        status="pending",
        payment_method_status="pending",
        solfege_slot_status="pending" if quote.estimated_solfege_level else "not_applicable",
        payload={},
        created_at=now,
        updated_at=now,
    )
    db.add(followup)
    db.flush()
    return followup


def _ensure_pending_client_from_prospect(db: Session, quote: Quote) -> UUID | None:
    if quote.context_type != "acquisition":
        return quote.client_id
    if quote.client_id is not None:
        return quote.client_id
    if quote.prospect_id is None:
        return None

    prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id).with_for_update())
    if prospect is None:
        return None
    if prospect.linked_client_id is not None:
        quote.client_id = prospect.linked_client_id
        db.add(quote)
        return prospect.linked_client_id

    if not prospect.email:
        return None
    existing = db.scalar(select(User).where(User.email == prospect.email.strip().lower()).limit(1))
    if existing is not None:
        prospect.linked_client_id = existing.id
        prospect.status = "converted"
        prospect.updated_at = _utcnow()
        quote.client_id = existing.id
        db.add_all([prospect, quote])
        return existing.id

    now = _utcnow()
    generated_password = hash_password(secrets.token_urlsafe(24))
    client = User(
        email=prospect.email.strip().lower(),
        hashed_password=generated_password,
        role=UserRole.CLIENT,
        first_name=prospect.first_name,
        last_name=prospect.last_name,
        phone=prospect.phone,
        mobile_phone_1=prospect.phone,
        client_status=ClientStatus.PENDING,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(client)
    db.flush()

    prospect.linked_client_id = client.id
    prospect.status = "converted"
    prospect.updated_at = now
    quote.client_id = client.id
    db.add_all([prospect, quote])
    return client.id


@router.post("/public/quotes/{quote_id}/approve", response_model=QuotePublicOut)
def public_approve_quote(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> QuotePublicOut:
    quote = _load_quote(db, quote_id, lock=True)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    if quote.status not in {"sent", "change_requested"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote cannot be approved in current status")

    now = _utcnow()
    quote.status = "approved"
    quote.approved_at = now
    quote.updated_at = now

    target_client_id = _ensure_pending_client_from_prospect(db, quote)
    followup = _ensure_followup(db, quote)
    if target_client_id is not None:
        followup.target_client_id = target_client_id
    followup.status = "pending"
    followup.updated_at = now
    db.add(followup)

    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_approved",
            actor_type="prospect",
            payload={"target_client_id": str(target_client_id) if target_client_id else None},
            created_at=now,
        )
    )

    db.add(quote)
    db.commit()
    db.refresh(quote)
    lines = _load_quote_lines(db, quote.id)
    return QuotePublicOut(
        quote=_quote_out(quote),
        lines=[_line_out(row) for row in lines],
        payment_schedule=list((quote.payment_terms_snapshot or {}).get("schedule", [])),
    )


@router.post("/public/quotes/{quote_id}/reject", response_model=QuotePublicOut)
def public_reject_quote(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> QuotePublicOut:
    quote = _load_quote(db, quote_id, lock=True)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    if quote.status not in {"sent", "change_requested"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote cannot be rejected in current status")

    now = _utcnow()
    quote.status = "rejected"
    quote.rejected_at = now
    quote.updated_at = now
    db.add(quote)
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_rejected",
            actor_type="prospect",
            payload={},
            created_at=now,
        )
    )
    db.commit()
    db.refresh(quote)
    lines = _load_quote_lines(db, quote.id)
    return QuotePublicOut(
        quote=_quote_out(quote),
        lines=[_line_out(row) for row in lines],
        payment_schedule=list((quote.payment_terms_snapshot or {}).get("schedule", [])),
    )


@router.post("/public/quotes/{quote_id}/change-request", response_model=QuotePublicOut)
def public_change_request_quote(
    quote_id: UUID,
    payload: QuoteChangeRequestIn,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> QuotePublicOut:
    quote = _load_quote(db, quote_id, lock=True)
    if quote.public_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid quote token")
    if quote.status not in {"sent", "change_requested"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote cannot accept change request in current status")

    now = _utcnow()
    quote.status = "change_requested"
    quote.updated_at = now
    db.add(quote)
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_change_requested",
            actor_type="prospect",
            payload={"message": payload.message.strip()},
            created_at=now,
        )
    )
    db.commit()
    db.refresh(quote)
    lines = _load_quote_lines(db, quote.id)
    return QuotePublicOut(
        quote=_quote_out(quote),
        lines=[_line_out(row) for row in lines],
        payment_schedule=list((quote.payment_terms_snapshot or {}).get("schedule", [])),
    )


@router.get("/public/quotes/{quote_id}/pdf")
def public_quote_pdf(
    quote_id: UUID,
    t: str = Query(..., min_length=10),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    quote = _load_quote(db, quote_id)
    if quote.pdf_token != t:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid PDF token")
    lines = _load_quote_lines(db, quote.id)
    pdf_bytes = render_quote_pdf(quote=quote, lines=lines)
    filename = f"devis-{quote.quote_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/quote-followups/{followup_id}", response_model=QuoteFollowupOut)
def get_quote_followup(
    followup_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")
    return _followup_out(row)


@router.get("/quote-followups", response_model=list[QuoteFollowupOut])
def list_quote_followups(
    quote_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteFollowupOut]:
    stmt = select(QuoteAcceptanceFollowup)
    if quote_id is not None:
        stmt = stmt.where(QuoteAcceptanceFollowup.quote_id == quote_id)
    if status_filter:
        stmt = stmt.where(QuoteAcceptanceFollowup.status == status_filter.strip())
    rows = db.scalars(stmt.order_by(QuoteAcceptanceFollowup.updated_at.desc(), QuoteAcceptanceFollowup.created_at.desc()).limit(500)).all()
    return [_followup_out(row) for row in rows]


@router.patch("/quote-followups/{followup_id}", response_model=QuoteFollowupOut)
def update_quote_followup(
    followup_id: UUID,
    payload: QuoteFollowupUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")

    if payload.status is not None:
        row.status = payload.status
    if payload.payment_method_status is not None:
        row.payment_method_status = payload.payment_method_status
    if payload.solfege_slot_status is not None:
        row.solfege_slot_status = payload.solfege_slot_status
    if payload.payload is not None:
        row.payload = payload.payload
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _followup_out(row)


@router.post("/quote-followups/{followup_id}/select-solfege-slot", response_model=QuoteFollowupOut)
def select_quote_followup_solfege_slot(
    followup_id: UUID,
    payload: QuoteFollowupSlotRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")

    row.payload = {**(row.payload or {}), "selected_solfege_slot": payload.slot}
    row.solfege_slot_status = "chosen"
    row.status = "partially_configured"
    row.updated_at = _utcnow()

    quote = _load_quote(db, row.quote_id, lock=True)
    quote.selected_solfege_slot = payload.slot
    quote.updated_at = _utcnow()
    db.add_all([row, quote])
    db.commit()
    db.refresh(row)
    return _followup_out(row)


@router.post("/quote-followups/{followup_id}/change-payment-method", response_model=QuoteFollowupOut)
def change_quote_followup_payment_method(
    followup_id: UUID,
    payload: QuoteFollowupPaymentMethodRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")

    quote = _load_quote(db, row.quote_id, lock=True)
    row.payload = {
        **(row.payload or {}),
        "payment_method_code": payload.payment_method_code,
        "payment_plan_id": str(payload.payment_plan_id) if payload.payment_plan_id else None,
    }
    row.payment_method_status = "changed"
    row.status = "partially_configured"
    row.updated_at = _utcnow()

    if payload.payment_plan_id is not None:
        plan = db.scalar(select(PaymentPlan).where(PaymentPlan.id == payload.payment_plan_id))
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment plan not found")
        quote.payment_plan_id = plan.id
        quote.payment_terms_snapshot = {
            "schedule": build_payment_schedule(
                PaymentPlanScheduleInput(
                    payment_method_code=plan.payment_method,
                    total_ttc=_q2(Decimal(quote.total_ttc or 0)),
                    registration_date=_utcnow().date(),
                    currency=(quote.currency or "EUR").upper(),
                )
            ),
            "currency": quote.currency,
            "payment_plan_code": plan.code,
        }
    quote.updated_at = _utcnow()

    db.add_all([row, quote])
    db.commit()
    db.refresh(row)
    return _followup_out(row)


@router.post("/quote-followups/{followup_id}/finalize", response_model=QuoteFollowupOut)
def finalize_quote_followup(
    followup_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteFollowupOut:
    row = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.id == followup_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote follow-up not found")

    row.status = "completed"
    if row.payment_method_status in {"pending", "changed"}:
        row.payment_method_status = "validated"
    if row.solfege_slot_status == "chosen":
        row.solfege_slot_status = "validated"
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _followup_out(row)


@router.post("/internal/jobs/run-quotes-daily")
def run_quotes_daily_job(
    limit: int = Query(default=2000, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> dict[str, object]:
    result = run_quote_daily_lifecycle_job(db, now=_utcnow(), limit=limit)
    db.commit()
    return {
        "checked": result.checked,
        "reminders_sent": result.reminders_sent,
        "expired": result.expired,
        "cancelled": result.cancelled,
        "archived_prospects": result.archived_prospects,
        "failed": result.failed,
        "job_run_id": str(result.job_run_id),
    }


@router.get("/quote-types", response_model=list[QuoteTypeOut])
def list_quote_types(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[QuoteTypeOut]:
    stmt = select(QuoteType)
    if active_only:
        stmt = stmt.where(QuoteType.is_active.is_(True))
    rows = db.scalars(stmt.order_by(QuoteType.name.asc())).all()
    return [_quote_type_out(row) for row in rows]


@router.post("/quote-types", response_model=QuoteTypeOut, status_code=status.HTTP_201_CREATED)
def create_quote_type(
    payload: QuoteTypeUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteTypeOut:
    now = _utcnow()
    row = QuoteType(
        code=payload.code.strip(),
        name=payload.name.strip(),
        description=payload.description,
        default_expiry_days=payload.default_expiry_days,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote type code already exists") from exc
    db.refresh(row)
    return _quote_type_out(row)


@router.patch("/quote-types/{quote_type_id}", response_model=QuoteTypeOut)
def update_quote_type(
    quote_type_id: UUID,
    payload: QuoteTypeUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> QuoteTypeOut:
    row = db.scalar(select(QuoteType).where(QuoteType.id == quote_type_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote type not found")
    row.code = payload.code.strip()
    row.name = payload.name.strip()
    row.description = payload.description
    row.default_expiry_days = payload.default_expiry_days
    row.is_active = payload.is_active
    row.updated_at = _utcnow()
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote type code already exists") from exc
    db.refresh(row)
    return _quote_type_out(row)


@router.delete("/quote-types/{quote_type_id}", status_code=status.HTTP_200_OK)
def delete_quote_type(
    quote_type_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(QuoteType).where(QuoteType.id == quote_type_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote type not found")
    in_use = db.scalar(select(Quote.id).where(Quote.quote_type_id == quote_type_id).limit(1))
    if in_use is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quote type is used by quotes")
    db.delete(row)
    db.commit()


@router.get("/pricing-catalogs", response_model=list[PricingCatalogOut])
def list_pricing_catalogs(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PricingCatalogOut]:
    stmt = select(PricingCatalog)
    if active_only:
        stmt = stmt.where(PricingCatalog.is_active.is_(True))
    rows = db.scalars(stmt.order_by(PricingCatalog.effective_from.desc())).all()
    return [_pricing_catalog_out(row) for row in rows]


@router.post("/pricing-catalogs", response_model=PricingCatalogOut, status_code=status.HTTP_201_CREATED)
def create_pricing_catalog(
    payload: PricingCatalogUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingCatalogOut:
    now = _utcnow()
    row = PricingCatalog(
        name=payload.name.strip(),
        school_year_label=payload.school_year_label,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_default=payload.is_default,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    if payload.effective_to is not None and payload.effective_to < payload.effective_from:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="effective_to must be >= effective_from")
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_catalog_out(row)


@router.patch("/pricing-catalogs/{catalog_id}", response_model=PricingCatalogOut)
def update_pricing_catalog(
    catalog_id: UUID,
    payload: PricingCatalogUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingCatalogOut:
    row = db.scalar(select(PricingCatalog).where(PricingCatalog.id == catalog_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing catalog not found")
    if payload.effective_to is not None and payload.effective_to < payload.effective_from:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="effective_to must be >= effective_from")
    row.name = payload.name.strip()
    row.school_year_label = payload.school_year_label
    row.effective_from = payload.effective_from
    row.effective_to = payload.effective_to
    row.is_default = payload.is_default
    row.is_active = payload.is_active
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_catalog_out(row)


@router.delete("/pricing-catalogs/{catalog_id}", status_code=status.HTTP_200_OK)
def delete_pricing_catalog(
    catalog_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PricingCatalog).where(PricingCatalog.id == catalog_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing catalog not found")
    in_use = db.scalar(select(Quote.id).where(Quote.pricing_catalog_id == catalog_id).limit(1))
    if in_use is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pricing catalog is used by quotes")
    db.delete(row)
    db.commit()


@router.get("/pricing-activity-prices", response_model=list[PricingActivityPriceOut])
def list_pricing_activity_prices(
    catalog_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PricingActivityPriceOut]:
    stmt = select(PricingActivityPrice)
    if catalog_id is not None:
        stmt = stmt.where(PricingActivityPrice.catalog_id == catalog_id)
    rows = db.scalars(stmt.order_by(PricingActivityPrice.created_at.desc())).all()
    return [_pricing_activity_price_out(row) for row in rows]


@router.post("/pricing-activity-prices", response_model=PricingActivityPriceOut, status_code=status.HTTP_201_CREATED)
def upsert_pricing_activity_price(
    payload: PricingActivityPriceUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingActivityPriceOut:
    row = db.scalar(
        select(PricingActivityPrice)
        .where(
            PricingActivityPrice.catalog_id == payload.catalog_id,
            PricingActivityPrice.activity_id == payload.activity_id,
            PricingActivityPrice.location_id.is_(payload.location_id) if payload.location_id is None else PricingActivityPrice.location_id == payload.location_id,
            PricingActivityPrice.student_category.is_(payload.student_category) if payload.student_category is None else PricingActivityPrice.student_category == payload.student_category,
            PricingActivityPrice.pricing_unit == payload.pricing_unit,
        )
        .limit(1)
    )
    now = _utcnow()
    if row is None:
        row = PricingActivityPrice(
            catalog_id=payload.catalog_id,
            activity_id=payload.activity_id,
            location_id=payload.location_id,
            student_category=payload.student_category,
            pricing_unit=payload.pricing_unit,
            unit_price_ttc=payload.unit_price_ttc,
            currency=payload.currency.upper(),
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
    else:
        row.unit_price_ttc = payload.unit_price_ttc
        row.currency = payload.currency.upper()
        row.is_active = payload.is_active
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_activity_price_out(row)


@router.delete("/pricing-activity-prices/{price_id}", status_code=status.HTTP_200_OK)
def delete_pricing_activity_price(
    price_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PricingActivityPrice).where(PricingActivityPrice.id == price_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing activity price not found")
    db.delete(row)
    db.commit()


@router.get("/pricing-product-prices", response_model=list[PricingProductPriceOut])
def list_pricing_product_prices(
    catalog_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PricingProductPriceOut]:
    stmt = select(PricingProductPrice)
    if catalog_id is not None:
        stmt = stmt.where(PricingProductPrice.catalog_id == catalog_id)
    rows = db.scalars(stmt.order_by(PricingProductPrice.created_at.desc())).all()
    return [_pricing_product_price_out(row) for row in rows]


@router.post("/pricing-product-prices", response_model=PricingProductPriceOut, status_code=status.HTTP_201_CREATED)
def upsert_pricing_product_price(
    payload: PricingProductPriceUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingProductPriceOut:
    row = db.scalar(
        select(PricingProductPrice)
        .where(
            PricingProductPrice.catalog_id == payload.catalog_id,
            PricingProductPrice.product_id == payload.product_id,
        )
        .limit(1)
    )
    now = _utcnow()
    if row is None:
        row = PricingProductPrice(
            catalog_id=payload.catalog_id,
            product_id=payload.product_id,
            unit_price_ttc=payload.unit_price_ttc,
            currency=payload.currency.upper(),
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
    else:
        row.unit_price_ttc = payload.unit_price_ttc
        row.currency = payload.currency.upper()
        row.is_active = payload.is_active
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_product_price_out(row)


@router.delete("/pricing-product-prices/{price_id}", status_code=status.HTTP_200_OK)
def delete_pricing_product_price(
    price_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PricingProductPrice).where(PricingProductPrice.id == price_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing product price not found")
    db.delete(row)
    db.commit()


@router.get("/pricing-kit-prices", response_model=list[PricingKitPriceOut])
def list_pricing_kit_prices(
    catalog_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PricingKitPriceOut]:
    stmt = select(PricingKitPrice)
    if catalog_id is not None:
        stmt = stmt.where(PricingKitPrice.catalog_id == catalog_id)
    rows = db.scalars(stmt.order_by(PricingKitPrice.created_at.desc())).all()
    return [_pricing_kit_price_out(row) for row in rows]


@router.post("/pricing-kit-prices", response_model=PricingKitPriceOut, status_code=status.HTTP_201_CREATED)
def upsert_pricing_kit_price(
    payload: PricingKitPriceUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PricingKitPriceOut:
    row = db.scalar(
        select(PricingKitPrice)
        .where(
            PricingKitPrice.catalog_id == payload.catalog_id,
            PricingKitPrice.kit_id == payload.kit_id,
        )
        .limit(1)
    )
    now = _utcnow()
    if row is None:
        row = PricingKitPrice(
            catalog_id=payload.catalog_id,
            kit_id=payload.kit_id,
            unit_price_ttc=payload.unit_price_ttc,
            currency=payload.currency.upper(),
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
    else:
        row.unit_price_ttc = payload.unit_price_ttc
        row.currency = payload.currency.upper()
        row.is_active = payload.is_active
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pricing_kit_price_out(row)


@router.delete("/pricing-kit-prices/{price_id}", status_code=status.HTTP_200_OK)
def delete_pricing_kit_price(
    price_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PricingKitPrice).where(PricingKitPrice.id == price_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing kit price not found")
    db.delete(row)
    db.commit()


@router.get("/solfege-level-rules", response_model=list[SolfegeLevelRuleOut])
def list_solfege_level_rules(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[SolfegeLevelRuleOut]:
    stmt = select(SolfegeLevelRule)
    if active_only:
        stmt = stmt.where(SolfegeLevelRule.is_active.is_(True))
    rows = db.scalars(stmt.order_by(SolfegeLevelRule.level_code.asc(), SolfegeLevelRule.created_at.desc())).all()
    return [_solfege_rule_out(row) for row in rows]


@router.post("/solfege-level-rules", response_model=SolfegeLevelRuleOut, status_code=status.HTTP_201_CREATED)
def upsert_solfege_level_rule(
    payload: SolfegeLevelRuleUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> SolfegeLevelRuleOut:
    row = db.scalar(
        select(SolfegeLevelRule)
        .where(
            SolfegeLevelRule.level_code == payload.level_code,
            SolfegeLevelRule.location_id.is_(payload.location_id) if payload.location_id is None else SolfegeLevelRule.location_id == payload.location_id,
            SolfegeLevelRule.modality.is_(payload.modality) if payload.modality is None else SolfegeLevelRule.modality == payload.modality,
        )
        .limit(1)
    )
    now = _utcnow()
    if row is None:
        row = SolfegeLevelRule(
            level_code=payload.level_code,
            duration_minutes=payload.duration_minutes,
            allowed_weekdays=payload.allowed_weekdays,
            allowed_time_slots=payload.allowed_time_slots,
            location_id=payload.location_id,
            modality=payload.modality,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
    else:
        row.duration_minutes = payload.duration_minutes
        row.allowed_weekdays = payload.allowed_weekdays
        row.allowed_time_slots = payload.allowed_time_slots
        row.is_active = payload.is_active
        row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _solfege_rule_out(row)


@router.delete("/solfege-level-rules/{rule_id}", status_code=status.HTTP_200_OK)
def delete_solfege_level_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(SolfegeLevelRule).where(SolfegeLevelRule.id == rule_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solfege rule not found")
    db.delete(row)
    db.commit()


@router.get("/payment-plans", response_model=list[PaymentPlanOut])
def list_payment_plans(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[PaymentPlanOut]:
    stmt = select(PaymentPlan)
    if active_only:
        stmt = stmt.where(PaymentPlan.is_active.is_(True))
    rows = db.scalars(stmt.order_by(PaymentPlan.name.asc())).all()
    return [_payment_plan_out(row) for row in rows]


@router.post("/payment-plans", response_model=PaymentPlanOut, status_code=status.HTTP_201_CREATED)
def create_payment_plan(
    payload: PaymentPlanUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PaymentPlanOut:
    now = _utcnow()
    row = PaymentPlan(
        code=payload.code.strip(),
        name=payload.name.strip(),
        payment_method=payload.payment_method.strip(),
        schedule_type=payload.schedule_type.strip(),
        schedule_rules=payload.schedule_rules,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment plan code already exists") from exc
    db.refresh(row)
    return _payment_plan_out(row)


@router.patch("/payment-plans/{plan_id}", response_model=PaymentPlanOut)
def update_payment_plan(
    plan_id: UUID,
    payload: PaymentPlanUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> PaymentPlanOut:
    row = db.scalar(select(PaymentPlan).where(PaymentPlan.id == plan_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment plan not found")
    row.code = payload.code.strip()
    row.name = payload.name.strip()
    row.payment_method = payload.payment_method.strip()
    row.schedule_type = payload.schedule_type.strip()
    row.schedule_rules = payload.schedule_rules
    row.is_active = payload.is_active
    row.updated_at = _utcnow()
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment plan code already exists") from exc
    db.refresh(row)
    return _payment_plan_out(row)


@router.delete("/payment-plans/{plan_id}", status_code=status.HTTP_200_OK)
def delete_payment_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(PaymentPlan).where(PaymentPlan.id == plan_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment plan not found")
    in_use = db.scalar(select(Quote.id).where(Quote.payment_plan_id == row.id).limit(1))
    if in_use is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment plan is used by quotes")
    db.delete(row)
    db.commit()


@router.get("/cgv-versions", response_model=list[CgvVersionOut])
def list_cgv_versions(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[CgvVersionOut]:
    stmt = select(CgvVersion)
    if active_only:
        stmt = stmt.where(CgvVersion.is_active.is_(True))
    rows = db.scalars(stmt.order_by(CgvVersion.created_at.desc())).all()
    return [_cgv_out(row) for row in rows]


@router.post("/cgv-versions", response_model=CgvVersionOut, status_code=status.HTTP_201_CREATED)
def create_cgv_version(
    payload: CgvVersionUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CgvVersionOut:
    now = _utcnow()
    row = CgvVersion(
        version_label=payload.version_label.strip(),
        content=payload.content,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CGV version label already exists") from exc
    db.refresh(row)
    return _cgv_out(row)


@router.patch("/cgv-versions/{cgv_id}", response_model=CgvVersionOut)
def update_cgv_version(
    cgv_id: UUID,
    payload: CgvVersionUpsertRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CgvVersionOut:
    row = db.scalar(select(CgvVersion).where(CgvVersion.id == cgv_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CGV version not found")
    row.version_label = payload.version_label.strip()
    row.content = payload.content
    row.is_active = payload.is_active
    row.updated_at = _utcnow()
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CGV version label already exists") from exc
    db.refresh(row)
    return _cgv_out(row)


@router.delete("/cgv-versions/{cgv_id}", status_code=status.HTTP_200_OK)
def delete_cgv_version(
    cgv_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> None:
    row = db.scalar(select(CgvVersion).where(CgvVersion.id == cgv_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CGV version not found")
    db.delete(row)
    db.commit()
