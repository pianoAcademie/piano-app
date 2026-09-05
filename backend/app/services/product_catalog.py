from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, Location, Professor, SessionStatus
from app.models.client_record import ClientManualTransaction
from app.models.product_catalog import (
    CatalogProduct,
    ProductCategory,
    ProductLocationStock,
    ProductReorderStatus,
    ProductRequest,
    ProductRequestStatus,
    ProductStockMovement,
    ProductStockTransfer,
    StockMovementSourceType,
    StockMovementType,
    ProductTransferStatus,
)
from app.models.user import User
from app.services.family_billing import resolve_billing_profile
from app.services.session_teachers import effective_teacher_id_for_session


READY_FOR_DELIVERY_STATUSES = {
    ProductRequestStatus.INVOICE_TO_SEND,
    ProductRequestStatus.TO_DELIVER,
}
OPEN_FULFILLMENT_STATUSES = {
    ProductRequestStatus.WAITING_STOCK,
    *READY_FOR_DELIVERY_STATUSES,
}
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def display_name(user: User | None) -> str:
    if user is None:
        return ""
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    composed = f"{first} {last}".strip()
    if composed:
        return composed
    return user.email


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def ensure_product_stock_rows(db: Session, *, product_id: UUID) -> None:
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == product_id))
    if product is None or bool(product.is_virtual):
        return
    location_ids = db.scalars(select(Location.id)).all()
    if not location_ids:
        return
    existing = set(
        db.scalars(
            select(ProductLocationStock.location_id).where(ProductLocationStock.product_id == product_id)
        ).all()
    )
    now = utcnow()
    for location_id in location_ids:
        if location_id in existing:
            continue
        db.add(
            ProductLocationStock(
                product_id=product_id,
                location_id=location_id,
                inventory_quantity=0,
                real_quantity=0,
                estimated_quantity=0,
                inventory_updated_at=now,
                real_updated_at=now,
                estimated_updated_at=now,
                updated_at=now,
            )
        )


def get_or_create_stock_row(
    db: Session,
    *,
    product_id: UUID,
    location_id: UUID,
    lock: bool = False,
) -> ProductLocationStock:
    stmt = select(ProductLocationStock).where(
        ProductLocationStock.product_id == product_id,
        ProductLocationStock.location_id == location_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is not None:
        return row

    now = utcnow()
    row = ProductLocationStock(
        product_id=product_id,
        location_id=location_id,
        inventory_quantity=0,
        real_quantity=0,
        estimated_quantity=0,
        inventory_updated_at=now,
        real_updated_at=now,
        estimated_updated_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    if lock:
        row = db.scalar(stmt.with_for_update())
    return row if row is not None else row


def recalculate_product_global_stock(db: Session, *, product_id: UUID) -> None:
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == product_id).with_for_update())
    if product is None:
        return
    if product.is_virtual:
        product.stock_global_quantity = 0
        product.reserve_stock = 0
        if product.reorder_status != ProductReorderStatus.NORMAL:
            product.reorder_status = ProductReorderStatus.NORMAL
            product.reorder_status_updated_at = utcnow()
        product.updated_at = utcnow()
        db.add(product)
        return
    total = db.scalar(
        select(func.coalesce(func.sum(ProductLocationStock.real_quantity), 0)).where(
            ProductLocationStock.product_id == product_id
        )
    )
    from app.models.partition_distribution import PartitionMovement
    from app.services.partition_distribution import held_expression
    held = db.scalar(select(func.coalesce(func.sum(held_expression()), 0)).where(
        PartitionMovement.product_id == product_id, PartitionMovement.state == "CONFIRMED"))
    product.stock_global_quantity = int(total or 0) + int(held or 0)
    if int(product.stock_global_quantity or 0) < int(product.reserve_stock or 0):
        if product.reorder_status in {ProductReorderStatus.NORMAL, ProductReorderStatus.RECEIVED}:
            product.reorder_status = ProductReorderStatus.TO_ORDER
            product.reorder_status_updated_at = utcnow()
    elif product.reorder_status == ProductReorderStatus.TO_ORDER:
        product.reorder_status = ProductReorderStatus.NORMAL
        product.reorder_status_updated_at = utcnow()
    product.updated_at = utcnow()
    db.add(product)


def create_stock_movement(
    db: Session,
    *,
    product_id: UUID,
    location_id: UUID,
    movement_type: StockMovementType,
    quantity: Decimal,
    source_type: StockMovementSourceType,
    source_reference: str | None,
    note: str | None,
    attachment_key: str | None,
    created_by: UUID | None,
    occurred_at: datetime | None = None,
    meta: dict | None = None,
) -> ProductStockMovement:
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == product_id))
    if product is None:
        raise ValueError("Product not found")
    if product.is_virtual:
        raise ValueError("Virtual products have no stock management")

    quantized = Decimal(quantity).quantize(Decimal("0.01"))
    if movement_type == StockMovementType.STOCK_IN and quantized <= Decimal("0"):
        raise ValueError("Stock entry quantity must be positive")
    if movement_type == StockMovementType.ADJUSTMENT and quantized == Decimal("0"):
        raise ValueError("Adjustment quantity must be non-zero")
    if quantized != quantized.to_integral_value():
        raise ValueError("Stock quantity must be an integer unit")

    delta = int(quantized)
    now = utcnow()
    stock_row = get_or_create_stock_row(db, product_id=product_id, location_id=location_id, lock=True)
    stock_row.real_quantity = int(stock_row.real_quantity or 0) + delta
    stock_row.estimated_quantity = int(stock_row.estimated_quantity or 0) + delta
    stock_row.real_updated_at = now
    stock_row.estimated_updated_at = now
    stock_row.updated_at = now
    db.add(stock_row)

    movement = ProductStockMovement(
        product_id=product_id,
        location_id=location_id,
        movement_type=movement_type,
        quantity=quantized,
        occurred_at=occurred_at or now,
        source_type=source_type,
        source_reference=normalize_optional(source_reference),
        note=normalize_optional(note),
        attachment_key=normalize_optional(attachment_key),
        created_by=created_by,
        meta=meta,
        updated_at=now,
    )
    db.add(movement)

    recalculate_product_global_stock(db, product_id=product_id)
    db.flush()
    reconcile_waiting_product_requests(db, product_id=product_id, location_id=location_id, now=now)
    return movement


def find_recent_stock_movement_by_idempotency_key(
    db: Session,
    *,
    created_by: UUID | None,
    idempotency_key: str,
    movement_type: StockMovementType,
    within_minutes: int = 10,
) -> ProductStockMovement | None:
    if not created_by or not idempotency_key.strip():
        return None
    threshold = utcnow() - timedelta(minutes=max(within_minutes, 1))
    rows = db.scalars(
        select(ProductStockMovement)
        .where(
            ProductStockMovement.created_by == created_by,
            ProductStockMovement.movement_type == movement_type,
            ProductStockMovement.created_at >= threshold,
        )
        .order_by(ProductStockMovement.created_at.desc())
        .limit(100)
    ).all()
    for row in rows:
        if isinstance(row.meta, dict) and row.meta.get("idempotency_key") == idempotency_key:
            return row
    return None


def create_stock_transfer(
    db: Session,
    *,
    product_id: UUID,
    source_location_id: UUID,
    target_location_id: UUID,
    quantity: int,
    planned_transfer_date: date | None,
    assigned_to_user_id: UUID | None,
    requested_by_user_id: UUID | None,
    note: str | None,
) -> ProductStockTransfer:
    if source_location_id == target_location_id:
        raise ValueError("Source and target locations must be distinct")
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == product_id))
    if product is None:
        raise ValueError("Product not found")
    if product.is_virtual:
        raise ValueError("Virtual products do not support stock transfers")

    qty = max(int(quantity), 1)
    now = utcnow()
    source_stock = get_or_create_stock_row(db, product_id=product_id, location_id=source_location_id, lock=True)
    target_stock = get_or_create_stock_row(db, product_id=product_id, location_id=target_location_id, lock=True)

    source_stock.estimated_quantity = int(source_stock.estimated_quantity or 0) - qty
    source_stock.estimated_updated_at = now
    source_stock.updated_at = now
    db.add(source_stock)

    target_stock.estimated_quantity = int(target_stock.estimated_quantity or 0) + qty
    target_stock.estimated_updated_at = now
    target_stock.updated_at = now
    db.add(target_stock)

    transfer = ProductStockTransfer(
        product_id=product_id,
        source_location_id=source_location_id,
        target_location_id=target_location_id,
        quantity=qty,
        planned_transfer_date=planned_transfer_date,
        assigned_to_user_id=assigned_to_user_id,
        requested_by_user_id=requested_by_user_id,
        status=ProductTransferStatus.PENDING,
        note=normalize_optional(note),
        updated_at=now,
    )
    db.add(transfer)
    db.flush()

    recalculate_product_global_stock(db, product_id=product_id)
    return transfer


def mark_stock_transfer_done(
    db: Session,
    *,
    transfer: ProductStockTransfer,
    completed_by_user_id: UUID | None,
    completed_transfer_date: date | None,
    note: str | None,
) -> ProductStockTransfer:
    if transfer.status != ProductTransferStatus.PENDING:
        return transfer

    qty = int(transfer.quantity or 0)
    now = utcnow()
    source_stock = get_or_create_stock_row(db, product_id=transfer.product_id, location_id=transfer.source_location_id, lock=True)
    target_stock = get_or_create_stock_row(db, product_id=transfer.product_id, location_id=transfer.target_location_id, lock=True)

    source_stock.real_quantity = int(source_stock.real_quantity or 0) - qty
    source_stock.real_updated_at = now
    source_stock.updated_at = now
    db.add(source_stock)

    target_stock.real_quantity = int(target_stock.real_quantity or 0) + qty
    target_stock.real_updated_at = now
    target_stock.updated_at = now
    db.add(target_stock)

    transfer.status = ProductTransferStatus.DONE
    transfer.completed_by_user_id = completed_by_user_id
    transfer.completed_at = now
    transfer.completed_transfer_date = completed_transfer_date or now.date()
    if note is not None:
        transfer.note = normalize_optional(note)
    transfer.updated_at = now
    db.add(transfer)

    recalculate_product_global_stock(db, product_id=transfer.product_id)
    reconcile_waiting_product_requests(
        db,
        product_id=transfer.product_id,
        location_id=transfer.target_location_id,
        now=now,
    )
    return transfer


def cancel_stock_transfer(
    db: Session,
    *,
    transfer: ProductStockTransfer,
    note: str | None,
) -> ProductStockTransfer:
    if transfer.status != ProductTransferStatus.PENDING:
        return transfer

    qty = int(transfer.quantity or 0)
    now = utcnow()
    source_stock = get_or_create_stock_row(db, product_id=transfer.product_id, location_id=transfer.source_location_id, lock=True)
    target_stock = get_or_create_stock_row(db, product_id=transfer.product_id, location_id=transfer.target_location_id, lock=True)

    source_stock.estimated_quantity = int(source_stock.estimated_quantity or 0) + qty
    source_stock.estimated_updated_at = now
    source_stock.updated_at = now
    db.add(source_stock)

    target_stock.estimated_quantity = int(target_stock.estimated_quantity or 0) - qty
    target_stock.estimated_updated_at = now
    target_stock.updated_at = now
    db.add(target_stock)

    transfer.status = ProductTransferStatus.CANCELLED
    if note is not None:
        transfer.note = normalize_optional(note)
    transfer.updated_at = now
    db.add(transfer)

    recalculate_product_global_stock(db, product_id=transfer.product_id)
    return transfer


def find_next_in_person_delivery_session(
    db: Session,
    *,
    student_user_id: UUID,
    now: datetime | None = None,
) -> CourseSession | None:
    """Return the next confirmed, non-cancelled, physical lesson for a student."""
    reference = now or utcnow()
    candidates = db.scalars(
        select(CourseSession)
        .join(Booking, Booking.session_id == CourseSession.id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            Booking.user_id == student_user_id,
            Booking.status == BookingStatus.BOOKED,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= reference,
            Location.is_online.is_(False),
        )
        .order_by(CourseSession.start_at_utc.asc())
        .limit(100)
    ).all()
    for session_obj in candidates:
        professor_id = effective_teacher_id_for_session(session_obj)
        if professor_id is None:
            continue
        professor = db.scalar(select(Professor).where(Professor.id == professor_id))
        if professor is None or not professor.active or not professor.daily_schedule_email_enabled:
            continue
        lesson_date = session_obj.start_at_utc.astimezone(PARIS_TIMEZONE).date()
        if professor.last_daily_schedule_sent_on == lesson_date:
            continue
        return session_obj
    return None


def _reserved_physical_quantity(
    db: Session,
    *,
    product_id: UUID,
    location_id: UUID,
    exclude_request_id: UUID | None = None,
) -> int:
    stmt = select(func.coalesce(func.sum(ProductRequest.stock_reserved_quantity), 0)).where(
        ProductRequest.product_id == product_id,
        ProductRequest.location_id == location_id,
        ProductRequest.status.in_(READY_FOR_DELIVERY_STATUSES),
        ProductRequest.stock_reserved_quantity > 0,
    )
    if exclude_request_id is not None:
        stmt = stmt.where(ProductRequest.id != exclude_request_id)
    return int(db.scalar(stmt) or 0)


def _available_physical_quantity(
    db: Session,
    *,
    stock: ProductLocationStock,
    exclude_request_id: UUID | None = None,
) -> int:
    reserved = _reserved_physical_quantity(
        db,
        product_id=stock.product_id,
        location_id=stock.location_id,
        exclude_request_id=exclude_request_id,
    )
    return max(int(stock.real_quantity or 0) - reserved, 0)


def _find_stock_transfer_source(
    db: Session,
    *,
    product: CatalogProduct,
    target_location_id: UUID,
    quantity: int,
) -> ProductLocationStock | None:
    rows = db.scalars(
        select(ProductLocationStock).where(
            ProductLocationStock.product_id == product.id,
            ProductLocationStock.location_id != target_location_id,
        )
    ).all()
    candidates = [
        row
        for row in rows
        if _available_physical_quantity(db, stock=row) >= quantity
        and int(row.estimated_quantity or 0) >= quantity
    ]
    candidates.sort(
        key=lambda row: (
            0 if row.location_id == product.primary_location_id else 1,
            -_available_physical_quantity(db, stock=row),
            str(row.location_id),
        )
    )
    return candidates[0] if candidates else None


def _ready_status_for_request(request_row: ProductRequest) -> ProductRequestStatus:
    return ProductRequestStatus.INVOICE_TO_SEND if bool(request_row.should_bill) else ProductRequestStatus.TO_DELIVER


def _assign_request_to_next_session(
    db: Session,
    *,
    request_row: ProductRequest,
    now: datetime,
    move_estimated_demand: bool,
) -> CourseSession | None:
    session_obj = find_next_in_person_delivery_session(
        db,
        student_user_id=request_row.student_user_id,
        now=now,
    )
    previous_location_id = request_row.location_id
    next_location_id = session_obj.location_id if session_obj is not None else previous_location_id

    if next_location_id != previous_location_id and move_estimated_demand:
        quantity = max(int(request_row.quantity or 0), 1)
        previous_stock = get_or_create_stock_row(
            db,
            product_id=request_row.product_id,
            location_id=previous_location_id,
            lock=True,
        )
        next_stock = get_or_create_stock_row(
            db,
            product_id=request_row.product_id,
            location_id=next_location_id,
            lock=True,
        )
        previous_stock.estimated_quantity = int(previous_stock.estimated_quantity or 0) + quantity
        next_stock.estimated_quantity = int(next_stock.estimated_quantity or 0) - quantity
        previous_stock.estimated_updated_at = now
        next_stock.estimated_updated_at = now
        previous_stock.updated_at = now
        next_stock.updated_at = now
        db.add(previous_stock)
        db.add(next_stock)

        if request_row.stock_transfer_id is not None:
            linked_transfer = db.scalar(
                select(ProductStockTransfer).where(ProductStockTransfer.id == request_row.stock_transfer_id).with_for_update()
            )
            if linked_transfer is not None and linked_transfer.status == ProductTransferStatus.PENDING:
                cancel_stock_transfer(db, transfer=linked_transfer, note="Cours de remise modifié")
            request_row.stock_transfer_id = None
        request_row.stock_reserved_quantity = 0
        request_row.ready_at = None

    request_row.location_id = next_location_id
    request_row.assigned_session_id = session_obj.id if session_obj is not None else None
    request_row.assigned_professor_id = (
        effective_teacher_id_for_session(session_obj) if session_obj is not None else None
    )
    return session_obj


def prepare_product_request_fulfillment(
    db: Session,
    *,
    request_row: ProductRequest,
    actor_user_id: UUID | None,
    now: datetime | None = None,
    reserve_estimated_demand: bool = False,
) -> ProductRequest:
    """Assign the next lesson and expose a request only when stock is physically ready."""
    reference = now or utcnow()
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == request_row.product_id))
    if product is None:
        raise ValueError("Product not found")

    _assign_request_to_next_session(
        db,
        request_row=request_row,
        now=reference,
        move_estimated_demand=not reserve_estimated_demand,
    )
    quantity = max(int(request_row.quantity or 0), 1)

    if product.is_virtual:
        request_row.stock_reserved_quantity = 0
        request_row.status = _ready_status_for_request(request_row)
        request_row.ready_at = request_row.ready_at or reference
        request_row.updated_at = reference
        db.add(request_row)
        return request_row

    target_stock = get_or_create_stock_row(
        db,
        product_id=request_row.product_id,
        location_id=request_row.location_id,
        lock=True,
    )
    if reserve_estimated_demand:
        target_stock.estimated_quantity = int(target_stock.estimated_quantity or 0) - quantity
        target_stock.estimated_updated_at = reference
        target_stock.updated_at = reference
        db.add(target_stock)

    available_here = _available_physical_quantity(
        db,
        stock=target_stock,
        exclude_request_id=request_row.id,
    )
    if available_here >= quantity:
        if request_row.stock_transfer_id is not None:
            linked_transfer = db.scalar(
                select(ProductStockTransfer).where(ProductStockTransfer.id == request_row.stock_transfer_id).with_for_update()
            )
            if linked_transfer is not None and linked_transfer.status == ProductTransferStatus.PENDING:
                cancel_stock_transfer(db, transfer=linked_transfer, note="Stock déjà disponible sur le lieu du cours")
            request_row.stock_transfer_id = None
        request_row.stock_reserved_quantity = quantity
        request_row.status = _ready_status_for_request(request_row)
        request_row.ready_at = request_row.ready_at or reference
        request_row.updated_at = reference
        db.add(request_row)
        return request_row

    request_row.status = ProductRequestStatus.WAITING_STOCK
    request_row.stock_reserved_quantity = 0
    request_row.ready_at = None
    request_row.updated_at = reference

    linked_transfer = None
    if request_row.stock_transfer_id is not None:
        linked_transfer = db.scalar(select(ProductStockTransfer).where(ProductStockTransfer.id == request_row.stock_transfer_id))
        if linked_transfer is not None and linked_transfer.status != ProductTransferStatus.PENDING:
            request_row.stock_transfer_id = None
            linked_transfer = None

    if linked_transfer is None:
        source_stock = _find_stock_transfer_source(
            db,
            product=product,
            target_location_id=request_row.location_id,
            quantity=quantity,
        )
        if source_stock is not None:
            transfer = create_stock_transfer(
                db,
                product_id=request_row.product_id,
                source_location_id=source_stock.location_id,
                target_location_id=request_row.location_id,
                quantity=quantity,
                planned_transfer_date=reference.date(),
                assigned_to_user_id=actor_user_id,
                requested_by_user_id=actor_user_id,
                note=f"Transfert pour demande produit {request_row.id}",
            )
            request_row.stock_transfer_id = transfer.id
        elif product.reorder_status in {ProductReorderStatus.NORMAL, ProductReorderStatus.RECEIVED}:
            product.reorder_status = ProductReorderStatus.TO_ORDER
            product.reorder_status_updated_at = reference
            product.updated_at = reference
            db.add(product)

    db.add(request_row)
    recalculate_product_global_stock(db, product_id=request_row.product_id)
    return request_row


def reconcile_waiting_product_requests(
    db: Session,
    *,
    product_id: UUID | None = None,
    location_id: UUID | None = None,
    now: datetime | None = None,
) -> int:
    stmt = select(ProductRequest).where(ProductRequest.status.in_(OPEN_FULFILLMENT_STATUSES))
    if product_id is not None:
        stmt = stmt.where(ProductRequest.product_id == product_id)
    if location_id is not None:
        stmt = stmt.where(ProductRequest.location_id == location_id)
    rows = db.scalars(stmt.order_by(ProductRequest.requested_at.asc()).with_for_update()).all()
    reference = now or utcnow()
    for row in rows:
        prepare_product_request_fulfillment(
            db,
            request_row=row,
            actor_user_id=None,
            now=reference,
            reserve_estimated_demand=False,
        )
    return len(rows)


def create_billable_product_transaction(
    db: Session,
    *,
    student: User,
    product: CatalogProduct,
    quantity: int,
    actor_user_id: UUID | None,
    occurred_at: datetime,
) -> ClientManualTransaction:
    quantity_value = max(int(quantity), 1)
    total_incl_vat = quantize_money(Decimal(product.price_incl_vat or Decimal("0.00")) * Decimal(quantity_value))
    vat_rate = Decimal(product.vat_rate or Decimal("0")).quantize(Decimal("0.001"))
    ratio = Decimal("1.000") + (vat_rate / Decimal("100"))
    amount_excl_vat = quantize_money(total_incl_vat / ratio) if ratio > Decimal("0") else total_incl_vat
    vat_amount = quantize_money(total_incl_vat - amount_excl_vat)

    billing_profile = resolve_billing_profile(db, student)
    category_name = None
    if product.category_id is not None:
        category_name = db.scalar(select(ProductCategory.name).where(ProductCategory.id == product.category_id))
    if category_name is None:
        category_name = db.scalar(
            select(ProductCategory.name)
            .where(ProductCategory.active.is_(True), ProductCategory.code == "PRODUCT")
            .limit(1)
        )
    if category_name is None:
        category_name = db.scalar(
            select(ProductCategory.name)
            .where(ProductCategory.active.is_(True), ProductCategory.name == "Produit")
            .limit(1)
        )

    row = ClientManualTransaction(
        user_id=billing_profile.id,
        student_user_id=student.id,
        actor_user_id=actor_user_id,
        transaction_type="CHARGE",
        status="PENDING",
        label=product.title,
        description=f"Produit catalogue ({quantity_value})",
        category=category_name,
        occurred_at=occurred_at,
        amount_excl_vat=amount_excl_vat,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total_incl_vat=total_incl_vat,
        currency=(billing_profile.preferred_currency or "EUR").upper(),
        reference=normalize_optional(product.barcode),
    )
    db.add(row)
    db.flush()
    return row


def apply_request_acceptance(
    db: Session,
    *,
    request_row: ProductRequest,
    actor_user_id: UUID | None,
    should_bill: bool,
    note: str | None,
) -> ProductRequest:
    if request_row.status != ProductRequestStatus.PROCESSING:
        return request_row

    now = utcnow()
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == request_row.product_id))
    student = db.scalar(select(User).where(User.id == request_row.student_user_id))
    if product is None or student is None:
        raise ValueError("Product or student not found")

    requested_quantity = max(int(request_row.quantity or 0), 1)
    transaction = None
    if should_bill:
        transaction = create_billable_product_transaction(
            db,
            student=student,
            product=product,
            quantity=requested_quantity,
            actor_user_id=actor_user_id,
            occurred_at=now,
        )

    request_row.accepted = True
    request_row.should_bill = should_bill
    request_row.manual_transaction_id = transaction.id if transaction is not None else None
    request_row.admin_reviewed_by_user_id = actor_user_id
    request_row.admin_reviewed_at = now
    if note is not None:
        request_row.note = normalize_optional(note)
    request_row.updated_at = now
    db.add(request_row)

    prepare_product_request_fulfillment(
        db,
        request_row=request_row,
        actor_user_id=actor_user_id,
        now=now,
        reserve_estimated_demand=not product.is_virtual,
    )

    recalculate_product_global_stock(db, product_id=request_row.product_id)
    return request_row


def mark_request_rejected(
    *,
    request_row: ProductRequest,
    actor_user_id: UUID | None,
    note: str | None,
) -> ProductRequest:
    if request_row.status != ProductRequestStatus.PROCESSING:
        return request_row

    now = utcnow()
    request_row.status = ProductRequestStatus.REJECTED
    request_row.accepted = False
    request_row.should_bill = False
    request_row.admin_reviewed_by_user_id = actor_user_id
    request_row.admin_reviewed_at = now
    if note is not None:
        request_row.note = normalize_optional(note)
    request_row.updated_at = now
    return request_row


def mark_request_delivered(
    db: Session,
    *,
    request_row: ProductRequest,
    marker_user_id: UUID | None,
    delivered_by_user_id: UUID | None,
    note: str | None,
) -> ProductRequest:
    if request_row.status not in READY_FOR_DELIVERY_STATUSES:
        return request_row

    # The repertoire distribution screen may already have recorded this handover.
    # Keep the older catalogue action from debiting a second physical copy.
    from app.models.partition_distribution import PartitionMovement
    from app.models.repertoire import StudentSheetMusic
    from fastapi import HTTPException
    db.scalar(select(CatalogProduct).where(CatalogProduct.id == request_row.product_id).with_for_update())
    db.scalar(select(User).where(User.id == request_row.student_user_id).with_for_update())
    if db.scalar(select(PartitionMovement.id).join(StudentSheetMusic, StudentSheetMusic.id == PartitionMovement.assignment_id).where(
        StudentSheetMusic.student_id == request_row.student_user_id,
        PartitionMovement.product_id == request_row.product_id,
        PartitionMovement.kind == "DELIVERY", PartitionMovement.state == "CONFIRMED")):
        raise HTTPException(409, "Cette partition a déjà été remise depuis le suivi pédagogique. Aucun nouveau retrait effectué.")

    now = utcnow()
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == request_row.product_id))
    if product is not None and not product.is_virtual:
        stock = get_or_create_stock_row(
            db,
            product_id=request_row.product_id,
            location_id=request_row.location_id,
            lock=True,
        )
        stock.real_quantity = int(stock.real_quantity or 0) - int(request_row.quantity or 0)
        stock.real_updated_at = now
        stock.updated_at = now
        db.add(stock)

    request_row.status = ProductRequestStatus.DELIVERED
    request_row.delivered_by_user_id = delivered_by_user_id or marker_user_id
    request_row.delivery_marked_by_user_id = marker_user_id
    request_row.delivery_marked_at = now
    request_row.stock_reserved_quantity = 0
    if note is not None:
        request_row.note = normalize_optional(note)
    request_row.updated_at = now
    db.add(request_row)

    recalculate_product_global_stock(db, product_id=request_row.product_id)
    return request_row


def reset_inventory_stock(
    db: Session,
    *,
    product_id: UUID,
    location_id: UUID,
    inventory_quantity: int,
    inventory_date,
) -> ProductLocationStock:
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == product_id))
    if product is None:
        raise ValueError("Product not found")
    if product.is_virtual:
        raise ValueError("Virtual products do not support stock inventory")
    row = get_or_create_stock_row(db, product_id=product_id, location_id=location_id, lock=True)
    now = utcnow()
    quantity = max(int(inventory_quantity), 0)
    row.inventory_quantity = quantity
    row.inventory_date = inventory_date
    row.real_quantity = quantity
    row.estimated_quantity = quantity
    row.inventory_updated_at = now
    row.real_updated_at = now
    row.estimated_updated_at = now
    row.updated_at = now
    db.add(row)
    recalculate_product_global_stock(db, product_id=product_id)
    reconcile_waiting_product_requests(db, product_id=product_id, location_id=location_id, now=now)
    return row
