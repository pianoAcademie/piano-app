from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Location
from app.models.product_catalog import (
    CatalogKit,
    CatalogKitItem,
    CatalogProduct,
    ProductCategory,
    ProductLocationStock,
    ProductReorderStatus,
    ProductRequest,
    ProductRequestSource,
    ProductRequestStatus,
    ProductStockMovement,
    ProductStockTransfer,
    StockMovementType,
    ProductTransferStatus,
)
from app.models.user import User, UserRole
from app.schemas.catalog_admin import (
    AdminCatalogCategoryCreateRequest,
    AdminCatalogCategoryOut,
    AdminCatalogCategoryUpdateRequest,
    AdminCatalogKitCreateRequest,
    AdminCatalogKitItemOut,
    AdminCatalogKitOut,
    AdminCatalogKitUpdateRequest,
    AdminCatalogProductCreateRequest,
    AdminCatalogProductOut,
    AdminCatalogProductUpdateRequest,
    AdminCatalogReorderProductOut,
    AdminCatalogReorderStatusUpdateRequest,
    AdminCatalogRequestCreateRequest,
    AdminCatalogRequestDeliverRequest,
    AdminCatalogRequestOut,
    AdminCatalogRequestReviewRequest,
    AdminCatalogStockInventoryUpdateRequest,
    AdminCatalogStockOut,
    AdminCatalogStockTransferCancelRequest,
    AdminCatalogStockTransferCompleteRequest,
    AdminCatalogStockTransferCreateRequest,
    AdminCatalogStockTransferOut,
    AdminCatalogProductStockOut,
    AdminStockAdjustmentCreateRequest,
    AdminStockEntryCreateRequest,
    AdminStockEntryCreateResponse,
    AdminStockMovementListOut,
    AdminStockMovementOut,
    AdminStockSnapshotOut,
)
from app.services.product_catalog import (
    apply_request_acceptance,
    cancel_stock_transfer,
    create_stock_movement,
    create_stock_transfer,
    ensure_product_stock_rows,
    find_recent_stock_movement_by_idempotency_key,
    mark_stock_transfer_done,
    mark_request_delivered,
    mark_request_rejected,
    normalize_optional,
    recalculate_product_global_stock,
    reset_inventory_stock,
    utcnow,
)

router = APIRouter(prefix="/admin")


def _require_category(db: Session, category_id: UUID) -> ProductCategory:
    row = db.scalar(select(ProductCategory).where(ProductCategory.id == category_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return row


def _require_product(db: Session, product_id: UUID) -> CatalogProduct:
    row = db.scalar(select(CatalogProduct).where(CatalogProduct.id == product_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return row


def _require_kit(db: Session, kit_id: UUID) -> CatalogKit:
    row = db.scalar(select(CatalogKit).where(CatalogKit.id == kit_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kit not found")
    return row


def _require_location(db: Session, location_id: UUID) -> Location:
    row = db.scalar(select(Location).where(Location.id == location_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return row


def _require_transfer(db: Session, transfer_id: UUID) -> ProductStockTransfer:
    row = db.scalar(select(ProductStockTransfer).where(ProductStockTransfer.id == transfer_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")
    return row


def _require_student_client(db: Session, student_user_id: UUID) -> User:
    row = db.scalar(select(User).where(User.id == student_user_id, User.role == UserRole.CLIENT))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return row


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    combined = f"{first} {last}".strip()
    return combined or user.email


def _category_name_map(db: Session) -> dict[UUID, str]:
    rows = db.execute(select(ProductCategory.id, ProductCategory.name)).all()
    return {category_id: name for category_id, name in rows}


def _location_name_map(db: Session) -> dict[UUID, str]:
    rows = db.execute(select(Location.id, Location.name)).all()
    return {location_id: name for location_id, name in rows}


def _user_name_map(db: Session, user_ids: list[UUID]) -> dict[UUID, str]:
    unique_ids = list({value for value in user_ids if value is not None})
    if not unique_ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(unique_ids))).all()
    return {row.id: (_display_name(row) or row.email) for row in users}


def _product_out(
    row: CatalogProduct,
    category_name_by_id: dict[UUID, str],
    location_name_by_id: dict[UUID, str],
) -> AdminCatalogProductOut:
    return AdminCatalogProductOut(
        id=row.id,
        category_id=row.category_id,
        category_name=category_name_by_id.get(row.category_id) if row.category_id else None,
        primary_location_id=row.primary_location_id,
        primary_location_name=location_name_by_id.get(row.primary_location_id) if row.primary_location_id else None,
        title=row.title,
        barcode=row.barcode,
        price_excl_vat=Decimal(row.price_excl_vat),
        price_incl_vat=Decimal(row.price_incl_vat),
        vat_rate=Decimal(row.vat_rate),
        stock_global_quantity=int(row.stock_global_quantity or 0),
        reserve_stock=int(row.reserve_stock or 0),
        reorder_status=row.reorder_status,
        reorder_status_updated_at=row.reorder_status_updated_at,
        image_url=row.image_url,
        short_description=row.short_description,
        long_description=row.long_description,
        web_link=row.web_link,
        is_virtual=bool(row.is_virtual),
        purchasable_online=bool(row.purchasable_online),
        is_public=bool(row.is_public),
        active=bool(row.active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _transfer_out(
    row: ProductStockTransfer,
    *,
    product_title_by_id: dict[UUID, str],
    location_name_by_id: dict[UUID, str],
    user_name_by_id: dict[UUID, str],
) -> AdminCatalogStockTransferOut:
    return AdminCatalogStockTransferOut(
        id=row.id,
        product_id=row.product_id,
        product_title=product_title_by_id.get(row.product_id, "Produit"),
        source_location_id=row.source_location_id,
        source_location_name=location_name_by_id.get(row.source_location_id, "Lieu"),
        target_location_id=row.target_location_id,
        target_location_name=location_name_by_id.get(row.target_location_id, "Lieu"),
        quantity=int(row.quantity or 0),
        planned_transfer_date=row.planned_transfer_date,
        assigned_to_user_id=row.assigned_to_user_id,
        assigned_to_name=user_name_by_id.get(row.assigned_to_user_id) if row.assigned_to_user_id else None,
        requested_by_user_id=row.requested_by_user_id,
        requested_by_name=user_name_by_id.get(row.requested_by_user_id) if row.requested_by_user_id else None,
        status=row.status,
        completed_by_user_id=row.completed_by_user_id,
        completed_by_name=user_name_by_id.get(row.completed_by_user_id) if row.completed_by_user_id else None,
        completed_at=row.completed_at,
        completed_transfer_date=row.completed_transfer_date,
        note=row.note,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _stock_movement_out(
    row: ProductStockMovement,
    *,
    product_title_by_id: dict[UUID, str],
    location_name_by_id: dict[UUID, str],
    user_name_by_id: dict[UUID, str],
) -> AdminStockMovementOut:
    return AdminStockMovementOut(
        id=row.id,
        product_id=row.product_id,
        product_title=product_title_by_id.get(row.product_id, "Produit"),
        location_id=row.location_id,
        location_name=location_name_by_id.get(row.location_id, "Lieu"),
        movement_type=row.movement_type,
        quantity=Decimal(row.quantity or Decimal("0.00")),
        occurred_at=row.occurred_at,
        source_type=row.source_type,
        source_reference=row.source_reference,
        note=row.note,
        attachment_key=row.attachment_key,
        created_by=row.created_by,
        created_by_name=user_name_by_id.get(row.created_by) if row.created_by else None,
        meta=row.meta if isinstance(row.meta, dict) else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _stock_snapshot_out(db: Session, *, product_id: UUID, location_id: UUID) -> AdminStockSnapshotOut:
    product = _require_product(db, product_id)
    stock_row = db.scalar(
        select(ProductLocationStock).where(
            ProductLocationStock.product_id == product_id,
            ProductLocationStock.location_id == location_id,
        )
    )
    return AdminStockSnapshotOut(
        product_id=product.id,
        product_title=product.title,
        stock_global=int(product.stock_global_quantity or 0),
        stock_location=int(stock_row.real_quantity or 0) if stock_row is not None else 0,
        stock_reserved=int(product.reserve_stock or 0),
    )


def _kit_out(
    db: Session,
    row: CatalogKit,
    *,
    category_name_by_id: dict[UUID, str],
    product_title_by_id: dict[UUID, str],
    product_price_by_id: dict[UUID, Decimal],
) -> AdminCatalogKitOut:
    items_rows = db.scalars(
        select(CatalogKitItem)
        .where(CatalogKitItem.kit_id == row.id)
        .order_by(CatalogKitItem.display_order.asc(), CatalogKitItem.created_at.asc())
    ).all()
    items: list[AdminCatalogKitItemOut] = []
    computed = Decimal("0.00")
    for item in items_rows:
        unit_price = product_price_by_id.get(item.product_id, Decimal("0.00"))
        line_total = (unit_price * Decimal(item.quantity or 0)).quantize(Decimal("0.01"))
        computed = (computed + line_total).quantize(Decimal("0.01"))
        items.append(
            AdminCatalogKitItemOut(
                product_id=item.product_id,
                product_title=product_title_by_id.get(item.product_id, "Produit supprime"),
                quantity=int(item.quantity or 0),
                display_order=int(item.display_order or 0),
                unit_price_incl_vat=unit_price,
                line_total_incl_vat=line_total,
            )
        )

    return AdminCatalogKitOut(
        id=row.id,
        category_id=row.category_id,
        category_name=category_name_by_id.get(row.category_id) if row.category_id else None,
        title=row.title,
        image_url=row.image_url,
        short_description=row.short_description,
        long_description=row.long_description,
        price_incl_vat=Decimal(row.price_incl_vat),
        vat_rate=Decimal(row.vat_rate),
        computed_price_incl_vat=computed,
        purchasable_online=bool(row.purchasable_online),
        is_public=bool(row.is_public),
        active=bool(row.active),
        items=items,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _request_out(db: Session, row: ProductRequest) -> AdminCatalogRequestOut:
    users = {
        user.id: user
        for user in db.scalars(
            select(User).where(
                User.id.in_(
                    [
                        value
                        for value in [
                            row.student_user_id,
                            row.requested_by_user_id,
                            row.admin_reviewed_by_user_id,
                            row.delivered_by_user_id,
                            row.delivery_marked_by_user_id,
                        ]
                        if value is not None
                    ]
                )
            )
        ).all()
    }
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == row.product_id))
    location = db.scalar(select(Location).where(Location.id == row.location_id))
    stock = db.scalar(
        select(ProductLocationStock).where(
            ProductLocationStock.product_id == row.product_id,
            ProductLocationStock.location_id == row.location_id,
        )
    )

    student = users.get(row.student_user_id)
    is_virtual = bool(product.is_virtual) if product is not None else False
    return AdminCatalogRequestOut(
        id=row.id,
        student_user_id=row.student_user_id,
        student_name=_display_name(student) or "Client",
        product_id=row.product_id,
        product_title=product.title if product is not None else "Produit supprime",
        location_id=row.location_id,
        location_name=location.name if location is not None else "Lieu inconnu",
        quantity=int(row.quantity or 0),
        requested_by_user_id=row.requested_by_user_id,
        requested_by_name=_display_name(users.get(row.requested_by_user_id)),
        request_source=row.request_source,
        status=row.status,
        requested_at=row.requested_at,
        admin_reviewed_by_user_id=row.admin_reviewed_by_user_id,
        admin_reviewed_by_name=_display_name(users.get(row.admin_reviewed_by_user_id)),
        admin_reviewed_at=row.admin_reviewed_at,
        accepted=row.accepted,
        should_bill=row.should_bill,
        manual_transaction_id=row.manual_transaction_id,
        delivered_by_user_id=row.delivered_by_user_id,
        delivered_by_name=_display_name(users.get(row.delivered_by_user_id)),
        delivery_marked_by_user_id=row.delivery_marked_by_user_id,
        delivery_marked_by_name=_display_name(users.get(row.delivery_marked_by_user_id)),
        delivery_marked_at=row.delivery_marked_at,
        note=row.note,
        stock_real_quantity=(None if is_virtual else (int(stock.real_quantity) if stock is not None else None)),
        stock_estimated_quantity=(None if is_virtual else (int(stock.estimated_quantity) if stock is not None else None)),
    )


@router.get("/config/catalog/categories", response_model=list[AdminCatalogCategoryOut])
def list_admin_catalog_categories(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminCatalogCategoryOut]:
    stmt = select(ProductCategory)
    if not include_inactive:
        stmt = stmt.where(ProductCategory.active.is_(True))
    rows = db.scalars(stmt.order_by(ProductCategory.name.asc())).all()
    return [
        AdminCatalogCategoryOut(
            id=row.id,
            name=row.name,
            description=row.description,
            active=bool(row.active),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/config/catalog/categories", response_model=AdminCatalogCategoryOut, status_code=status.HTTP_201_CREATED)
def create_admin_catalog_category(
    payload: AdminCatalogCategoryCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogCategoryOut:
    normalized_name = payload.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Category name is required")

    existing = db.scalar(select(ProductCategory).where(ProductCategory.name.ilike(normalized_name)))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists")

    now = utcnow()
    row = ProductCategory(
        name=normalized_name,
        description=normalize_optional(payload.description),
        active=payload.active,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AdminCatalogCategoryOut(
        id=row.id,
        name=row.name,
        description=row.description,
        active=bool(row.active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.put("/config/catalog/categories/{category_id}", response_model=AdminCatalogCategoryOut)
def update_admin_catalog_category(
    category_id: UUID,
    payload: AdminCatalogCategoryUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogCategoryOut:
    row = _require_category(db, category_id)
    normalized_name = payload.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Category name is required")

    duplicate = db.scalar(
        select(ProductCategory.id).where(ProductCategory.id != row.id, ProductCategory.name.ilike(normalized_name))
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists")

    row.name = normalized_name
    row.description = normalize_optional(payload.description)
    row.active = payload.active
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)

    return AdminCatalogCategoryOut(
        id=row.id,
        name=row.name,
        description=row.description,
        active=bool(row.active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete(
    "/config/catalog/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_admin_catalog_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    row = _require_category(db, category_id)
    linked_product = db.scalar(select(CatalogProduct.id).where(CatalogProduct.category_id == row.id).limit(1))
    linked_kit = db.scalar(select(CatalogKit.id).where(CatalogKit.category_id == row.id).limit(1))
    if linked_product is not None or linked_kit is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category is still linked to products or kits",
        )
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/config/catalog/products", response_model=list[AdminCatalogProductOut])
def list_admin_catalog_products(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminCatalogProductOut]:
    stmt = select(CatalogProduct)
    if not include_inactive:
        stmt = stmt.where(CatalogProduct.active.is_(True))
    rows = db.scalars(stmt.order_by(CatalogProduct.title.asc())).all()
    for row in rows:
        ensure_product_stock_rows(db, product_id=row.id)
        recalculate_product_global_stock(db, product_id=row.id)
    if rows:
        db.flush()
    category_name_by_id = _category_name_map(db)
    location_name_by_id = _location_name_map(db)
    return [_product_out(row, category_name_by_id, location_name_by_id) for row in rows]


@router.post("/config/catalog/products", response_model=AdminCatalogProductOut, status_code=status.HTTP_201_CREATED)
def create_admin_catalog_product(
    payload: AdminCatalogProductCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogProductOut:
    if payload.category_id is not None:
        _require_category(db, payload.category_id)
    if payload.primary_location_id is not None:
        _require_location(db, payload.primary_location_id)

    now = utcnow()
    is_virtual = bool(payload.is_virtual)
    row = CatalogProduct(
        category_id=payload.category_id,
        primary_location_id=payload.primary_location_id,
        title=payload.title.strip(),
        barcode=normalize_optional(payload.barcode),
        price_excl_vat=Decimal(payload.price_excl_vat).quantize(Decimal("0.01")),
        price_incl_vat=Decimal(payload.price_incl_vat).quantize(Decimal("0.01")),
        vat_rate=Decimal(payload.vat_rate).quantize(Decimal("0.001")),
        reserve_stock=(0 if is_virtual else max(int(payload.reserve_stock or 0), 0)),
        reorder_status=(ProductReorderStatus.NORMAL if is_virtual else payload.reorder_status),
        reorder_status_updated_at=now,
        image_url=normalize_optional(payload.image_url),
        short_description=normalize_optional(payload.short_description),
        long_description=normalize_optional(payload.long_description),
        web_link=normalize_optional(payload.web_link),
        is_virtual=is_virtual,
        purchasable_online=payload.purchasable_online,
        is_public=payload.is_public,
        active=payload.active,
        updated_at=now,
    )
    db.add(row)
    db.flush()

    if not row.is_virtual:
        ensure_product_stock_rows(db, product_id=row.id)
        recalculate_product_global_stock(db, product_id=row.id)
    db.commit()
    db.refresh(row)

    category_name_by_id = _category_name_map(db)
    location_name_by_id = _location_name_map(db)
    return _product_out(row, category_name_by_id, location_name_by_id)


@router.put("/config/catalog/products/{product_id}", response_model=AdminCatalogProductOut)
def update_admin_catalog_product(
    product_id: UUID,
    payload: AdminCatalogProductUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogProductOut:
    row = _require_product(db, product_id)
    if payload.category_id is not None:
        _require_category(db, payload.category_id)
    if payload.primary_location_id is not None:
        _require_location(db, payload.primary_location_id)

    row.category_id = payload.category_id
    row.primary_location_id = payload.primary_location_id
    row.title = payload.title.strip()
    row.barcode = normalize_optional(payload.barcode)
    row.price_excl_vat = Decimal(payload.price_excl_vat).quantize(Decimal("0.01"))
    row.price_incl_vat = Decimal(payload.price_incl_vat).quantize(Decimal("0.01"))
    row.vat_rate = Decimal(payload.vat_rate).quantize(Decimal("0.001"))
    row.is_virtual = bool(payload.is_virtual)
    row.reserve_stock = 0 if row.is_virtual else max(int(payload.reserve_stock or 0), 0)
    target_reorder_status = ProductReorderStatus.NORMAL if row.is_virtual else payload.reorder_status
    if row.reorder_status != target_reorder_status:
        row.reorder_status = target_reorder_status
        row.reorder_status_updated_at = utcnow()
    row.image_url = normalize_optional(payload.image_url)
    row.short_description = normalize_optional(payload.short_description)
    row.long_description = normalize_optional(payload.long_description)
    row.web_link = normalize_optional(payload.web_link)
    row.purchasable_online = payload.purchasable_online
    row.is_public = payload.is_public
    row.active = payload.active
    row.updated_at = utcnow()

    if row.is_virtual:
        row.stock_global_quantity = 0
        db.execute(delete(ProductLocationStock).where(ProductLocationStock.product_id == row.id))
    else:
        ensure_product_stock_rows(db, product_id=row.id)
        recalculate_product_global_stock(db, product_id=row.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    category_name_by_id = _category_name_map(db)
    location_name_by_id = _location_name_map(db)
    return _product_out(row, category_name_by_id, location_name_by_id)


@router.delete(
    "/config/catalog/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_admin_catalog_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    row = _require_product(db, product_id)
    linked_request = db.scalar(select(ProductRequest.id).where(ProductRequest.product_id == row.id).limit(1))
    linked_kit_item = db.scalar(select(CatalogKitItem.id).where(CatalogKitItem.product_id == row.id).limit(1))
    if linked_request is not None or linked_kit_item is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product is used in requests or kits")

    db.execute(delete(ProductLocationStock).where(ProductLocationStock.product_id == row.id))
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/config/catalog/kits", response_model=list[AdminCatalogKitOut])
def list_admin_catalog_kits(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminCatalogKitOut]:
    stmt = select(CatalogKit)
    if not include_inactive:
        stmt = stmt.where(CatalogKit.active.is_(True))
    rows = db.scalars(stmt.order_by(CatalogKit.title.asc())).all()

    category_name_by_id = _category_name_map(db)
    product_rows = db.execute(select(CatalogProduct.id, CatalogProduct.title, CatalogProduct.price_incl_vat)).all()
    product_title_by_id = {product_id: title for product_id, title, _ in product_rows}
    product_price_by_id = {product_id: Decimal(price_incl_vat or Decimal("0.00")) for product_id, _, price_incl_vat in product_rows}
    return [
        _kit_out(
            db,
            row,
            category_name_by_id=category_name_by_id,
            product_title_by_id=product_title_by_id,
            product_price_by_id=product_price_by_id,
        )
        for row in rows
    ]


@router.post("/config/catalog/kits", response_model=AdminCatalogKitOut, status_code=status.HTTP_201_CREATED)
def create_admin_catalog_kit(
    payload: AdminCatalogKitCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogKitOut:
    if payload.category_id is not None:
        _require_category(db, payload.category_id)

    row = CatalogKit(
        category_id=payload.category_id,
        title=payload.title.strip(),
        image_url=normalize_optional(payload.image_url),
        short_description=normalize_optional(payload.short_description),
        long_description=normalize_optional(payload.long_description),
        price_incl_vat=Decimal(payload.price_incl_vat).quantize(Decimal("0.01")),
        vat_rate=Decimal(payload.vat_rate).quantize(Decimal("0.001")),
        purchasable_online=payload.purchasable_online,
        is_public=payload.is_public,
        active=payload.active,
        updated_at=utcnow(),
    )
    db.add(row)
    db.flush()

    for item in payload.items:
        _require_product(db, item.product_id)
        db.add(
            CatalogKitItem(
                kit_id=row.id,
                product_id=item.product_id,
                quantity=item.quantity,
                display_order=item.display_order,
            )
        )

    db.commit()
    db.refresh(row)

    category_name_by_id = _category_name_map(db)
    product_rows = db.execute(select(CatalogProduct.id, CatalogProduct.title, CatalogProduct.price_incl_vat)).all()
    product_title_by_id = {product_id: title for product_id, title, _ in product_rows}
    product_price_by_id = {product_id: Decimal(price_incl_vat or Decimal("0.00")) for product_id, _, price_incl_vat in product_rows}
    return _kit_out(
        db,
        row,
        category_name_by_id=category_name_by_id,
        product_title_by_id=product_title_by_id,
        product_price_by_id=product_price_by_id,
    )


@router.put("/config/catalog/kits/{kit_id}", response_model=AdminCatalogKitOut)
def update_admin_catalog_kit(
    kit_id: UUID,
    payload: AdminCatalogKitUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogKitOut:
    row = _require_kit(db, kit_id)
    if payload.category_id is not None:
        _require_category(db, payload.category_id)

    row.category_id = payload.category_id
    row.title = payload.title.strip()
    row.image_url = normalize_optional(payload.image_url)
    row.short_description = normalize_optional(payload.short_description)
    row.long_description = normalize_optional(payload.long_description)
    row.price_incl_vat = Decimal(payload.price_incl_vat).quantize(Decimal("0.01"))
    row.vat_rate = Decimal(payload.vat_rate).quantize(Decimal("0.001"))
    row.purchasable_online = payload.purchasable_online
    row.is_public = payload.is_public
    row.active = payload.active
    row.updated_at = utcnow()
    db.add(row)

    db.execute(delete(CatalogKitItem).where(CatalogKitItem.kit_id == row.id))
    for item in payload.items:
        _require_product(db, item.product_id)
        db.add(
            CatalogKitItem(
                kit_id=row.id,
                product_id=item.product_id,
                quantity=item.quantity,
                display_order=item.display_order,
            )
        )

    db.commit()
    db.refresh(row)

    category_name_by_id = _category_name_map(db)
    product_rows = db.execute(select(CatalogProduct.id, CatalogProduct.title, CatalogProduct.price_incl_vat)).all()
    product_title_by_id = {product_id: title for product_id, title, _ in product_rows}
    product_price_by_id = {product_id: Decimal(price_incl_vat or Decimal("0.00")) for product_id, _, price_incl_vat in product_rows}
    return _kit_out(
        db,
        row,
        category_name_by_id=category_name_by_id,
        product_title_by_id=product_title_by_id,
        product_price_by_id=product_price_by_id,
    )


@router.delete(
    "/config/catalog/kits/{kit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_admin_catalog_kit(
    kit_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    row = _require_kit(db, kit_id)
    db.execute(delete(CatalogKitItem).where(CatalogKitItem.kit_id == row.id))
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/config/catalog/stocks", response_model=list[AdminCatalogStockOut])
def list_admin_catalog_stocks(
    product_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminCatalogStockOut]:
    products = db.scalars(select(CatalogProduct).where(CatalogProduct.is_virtual.is_(False)).order_by(CatalogProduct.title.asc())).all()
    if product_id is not None:
        products = [row for row in products if row.id == product_id]
    for product in products:
        ensure_product_stock_rows(db, product_id=product.id)
        recalculate_product_global_stock(db, product_id=product.id)
    if products:
        db.flush()

    product_title_by_id = {row.id: row.title for row in products}
    location_name_by_id = {row.id: row.name for row in db.scalars(select(Location)).all()}

    stmt = (
        select(ProductLocationStock)
        .join(CatalogProduct, CatalogProduct.id == ProductLocationStock.product_id)
        .where(CatalogProduct.is_virtual.is_(False))
    )
    if product_id is not None:
        stmt = stmt.where(ProductLocationStock.product_id == product_id)
    rows = db.scalars(stmt.order_by(ProductLocationStock.product_id.asc(), ProductLocationStock.location_id.asc())).all()

    return [
        AdminCatalogStockOut(
            product_id=row.product_id,
            product_title=product_title_by_id.get(row.product_id, "Produit"),
            location_id=row.location_id,
            location_name=location_name_by_id.get(row.location_id, "Lieu"),
            inventory_quantity=int(row.inventory_quantity or 0),
            inventory_date=row.inventory_date,
            real_quantity=int(row.real_quantity or 0),
            estimated_quantity=int(row.estimated_quantity or 0),
            inventory_updated_at=row.inventory_updated_at,
            real_updated_at=row.real_updated_at,
            estimated_updated_at=row.estimated_updated_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post("/stock/entries", response_model=AdminStockEntryCreateResponse, status_code=status.HTTP_201_CREATED)
def create_admin_stock_entry(
    payload: AdminStockEntryCreateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AdminStockEntryCreateResponse:
    _require_product(db, payload.product_id)
    _require_location(db, payload.location_id)

    normalized_idempotency = (idempotency_key or "").strip()
    if normalized_idempotency:
        duplicate = find_recent_stock_movement_by_idempotency_key(
            db,
            created_by=actor.id,
            idempotency_key=normalized_idempotency,
            movement_type=StockMovementType.STOCK_IN,
            within_minutes=10,
        )
        if duplicate is not None:
            snapshot = _stock_snapshot_out(db, product_id=duplicate.product_id, location_id=duplicate.location_id)
            return AdminStockEntryCreateResponse(movement_id=duplicate.id, stock_snapshot=snapshot)

    meta = {"idempotency_key": normalized_idempotency} if normalized_idempotency else None
    try:
        movement = create_stock_movement(
            db,
            product_id=payload.product_id,
            location_id=payload.location_id,
            movement_type=StockMovementType.STOCK_IN,
            quantity=payload.quantity,
            source_type=payload.source_type,
            source_reference=payload.source_reference,
            note=payload.note,
            attachment_key=payload.attachment_key,
            created_by=actor.id,
            occurred_at=payload.occurred_at,
            meta=meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    db.commit()
    db.refresh(movement)
    snapshot = _stock_snapshot_out(db, product_id=payload.product_id, location_id=payload.location_id)
    return AdminStockEntryCreateResponse(movement_id=movement.id, stock_snapshot=snapshot)


@router.post("/stock/adjustments", response_model=AdminStockEntryCreateResponse, status_code=status.HTTP_201_CREATED)
def create_admin_stock_adjustment(
    payload: AdminStockAdjustmentCreateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AdminStockEntryCreateResponse:
    if payload.quantity == Decimal("0"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Adjustment quantity must be non-zero")
    _require_product(db, payload.product_id)
    _require_location(db, payload.location_id)

    normalized_idempotency = (idempotency_key or "").strip()
    if normalized_idempotency:
        duplicate = find_recent_stock_movement_by_idempotency_key(
            db,
            created_by=actor.id,
            idempotency_key=normalized_idempotency,
            movement_type=StockMovementType.ADJUSTMENT,
            within_minutes=10,
        )
        if duplicate is not None:
            snapshot = _stock_snapshot_out(db, product_id=duplicate.product_id, location_id=duplicate.location_id)
            return AdminStockEntryCreateResponse(movement_id=duplicate.id, stock_snapshot=snapshot)

    meta = {"idempotency_key": normalized_idempotency} if normalized_idempotency else None
    try:
        movement = create_stock_movement(
            db,
            product_id=payload.product_id,
            location_id=payload.location_id,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity=payload.quantity,
            source_type=payload.source_type,
            source_reference=payload.source_reference,
            note=payload.note,
            attachment_key=payload.attachment_key,
            created_by=actor.id,
            occurred_at=payload.occurred_at,
            meta=meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    db.commit()
    db.refresh(movement)
    snapshot = _stock_snapshot_out(db, product_id=payload.product_id, location_id=payload.location_id)
    return AdminStockEntryCreateResponse(movement_id=movement.id, stock_snapshot=snapshot)


@router.get("/stock/entries", response_model=AdminStockMovementListOut)
def list_admin_stock_entries(
    product_id: UUID | None = None,
    location_id: UUID | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    q: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminStockMovementListOut:
    q_normalized = q.strip()

    stmt = (
        select(ProductStockMovement)
        .join(CatalogProduct, CatalogProduct.id == ProductStockMovement.product_id)
        .join(Location, Location.id == ProductStockMovement.location_id)
        .where(ProductStockMovement.movement_type.in_([StockMovementType.STOCK_IN, StockMovementType.ADJUSTMENT]))
    )
    if product_id is not None:
        stmt = stmt.where(ProductStockMovement.product_id == product_id)
    if location_id is not None:
        stmt = stmt.where(ProductStockMovement.location_id == location_id)
    if from_date is not None:
        stmt = stmt.where(ProductStockMovement.occurred_at >= from_date)
    if to_date is not None:
        stmt = stmt.where(ProductStockMovement.occurred_at < (to_date + timedelta(days=1)))
    if q_normalized:
        ilike_pattern = f"%{q_normalized}%"
        stmt = stmt.where(
            or_(
                CatalogProduct.title.ilike(ilike_pattern),
                Location.name.ilike(ilike_pattern),
                ProductStockMovement.source_reference.ilike(ilike_pattern),
                ProductStockMovement.note.ilike(ilike_pattern),
            )
        )

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(ProductStockMovement.occurred_at.desc(), ProductStockMovement.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    product_title_by_id = {product_id_row: title for product_id_row, title in db.execute(select(CatalogProduct.id, CatalogProduct.title)).all()}
    location_name_by_id = _location_name_map(db)
    user_name_by_id = _user_name_map(db, [row.created_by for row in rows if row.created_by is not None])

    return AdminStockMovementListOut(
        items=[
            _stock_movement_out(
                row,
                product_title_by_id=product_title_by_id,
                location_name_by_id=location_name_by_id,
                user_name_by_id=user_name_by_id,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/config/catalog/products/{product_id}/stock", response_model=AdminCatalogProductStockOut)
def get_admin_catalog_product_stock(
    product_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogProductStockOut:
    product = _require_product(db, product_id)
    if product.is_virtual:
        return AdminCatalogProductStockOut(
            product_id=product.id,
            product_title=product.title,
            stock_global=0,
            stock_reserved=0,
            stock_by_location=[],
            recent_movements=[],
        )

    ensure_product_stock_rows(db, product_id=product.id)
    recalculate_product_global_stock(db, product_id=product.id)
    db.flush()

    location_name_by_id = _location_name_map(db)
    stock_rows = db.scalars(
        select(ProductLocationStock)
        .where(ProductLocationStock.product_id == product.id)
        .order_by(ProductLocationStock.location_id.asc())
    ).all()
    stock_by_location = [
        AdminCatalogStockOut(
            product_id=row.product_id,
            product_title=product.title,
            location_id=row.location_id,
            location_name=location_name_by_id.get(row.location_id, "Lieu"),
            inventory_quantity=int(row.inventory_quantity or 0),
            inventory_date=row.inventory_date,
            real_quantity=int(row.real_quantity or 0),
            estimated_quantity=int(row.estimated_quantity or 0),
            inventory_updated_at=row.inventory_updated_at,
            real_updated_at=row.real_updated_at,
            estimated_updated_at=row.estimated_updated_at,
            updated_at=row.updated_at,
        )
        for row in stock_rows
    ]

    recent_rows = db.scalars(
        select(ProductStockMovement)
        .where(ProductStockMovement.product_id == product.id)
        .order_by(ProductStockMovement.occurred_at.desc(), ProductStockMovement.created_at.desc())
        .limit(10)
    ).all()
    user_name_by_id = _user_name_map(db, [row.created_by for row in recent_rows if row.created_by is not None])
    product_title_by_id = {product.id: product.title}
    recent_movements = [
        _stock_movement_out(
            row,
            product_title_by_id=product_title_by_id,
            location_name_by_id=location_name_by_id,
            user_name_by_id=user_name_by_id,
        )
        for row in recent_rows
    ]

    return AdminCatalogProductStockOut(
        product_id=product.id,
        product_title=product.title,
        stock_global=int(product.stock_global_quantity or 0),
        stock_reserved=int(product.reserve_stock or 0),
        stock_by_location=stock_by_location,
        recent_movements=recent_movements,
    )


@router.put("/config/catalog/stocks/{product_id}/{location_id}/inventory", response_model=AdminCatalogStockOut)
def update_admin_catalog_stock_inventory(
    product_id: UUID,
    location_id: UUID,
    payload: AdminCatalogStockInventoryUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogStockOut:
    product = _require_product(db, product_id)
    if product.is_virtual:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Virtual products have no stock management")
    location = _require_location(db, location_id)
    row = reset_inventory_stock(
        db,
        product_id=product.id,
        location_id=location.id,
        inventory_quantity=payload.inventory_quantity,
        inventory_date=payload.inventory_date,
    )
    db.commit()
    db.refresh(row)

    return AdminCatalogStockOut(
        product_id=row.product_id,
        product_title=product.title,
        location_id=row.location_id,
        location_name=location.name,
        inventory_quantity=int(row.inventory_quantity or 0),
        inventory_date=row.inventory_date,
        real_quantity=int(row.real_quantity or 0),
        estimated_quantity=int(row.estimated_quantity or 0),
        inventory_updated_at=row.inventory_updated_at,
        real_updated_at=row.real_updated_at,
        estimated_updated_at=row.estimated_updated_at,
        updated_at=row.updated_at,
    )


@router.get("/config/catalog/reorder-products", response_model=list[AdminCatalogReorderProductOut])
def list_admin_catalog_reorder_products(
    status_filter: ProductReorderStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminCatalogReorderProductOut]:
    rows = db.scalars(select(CatalogProduct).where(CatalogProduct.is_virtual.is_(False)).order_by(CatalogProduct.title.asc())).all()
    for row in rows:
        ensure_product_stock_rows(db, product_id=row.id)
        recalculate_product_global_stock(db, product_id=row.id)
    if rows:
        db.flush()

    category_name_by_id = _category_name_map(db)
    location_name_by_id = _location_name_map(db)
    filtered = rows if status_filter is None else [row for row in rows if row.reorder_status == status_filter]
    return [
        AdminCatalogReorderProductOut(
            product_id=row.id,
            title=row.title,
            category_name=category_name_by_id.get(row.category_id) if row.category_id else None,
            stock_global_quantity=int(row.stock_global_quantity or 0),
            reserve_stock=int(row.reserve_stock or 0),
            reorder_status=row.reorder_status,
            reorder_status_updated_at=row.reorder_status_updated_at,
            primary_location_id=row.primary_location_id,
            primary_location_name=location_name_by_id.get(row.primary_location_id) if row.primary_location_id else None,
        )
        for row in filtered
        if int(row.stock_global_quantity or 0) < int(row.reserve_stock or 0) or status_filter is not None
    ]


@router.post("/config/catalog/reorder-products/{product_id}/status", response_model=AdminCatalogReorderProductOut)
def update_admin_catalog_reorder_status(
    product_id: UUID,
    payload: AdminCatalogReorderStatusUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogReorderProductOut:
    row = _require_product(db, product_id)
    if row.is_virtual:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Virtual products have no reorder workflow")
    row.reorder_status = payload.reorder_status
    row.reorder_status_updated_at = utcnow()
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)

    category_name = None
    if row.category_id is not None:
        category_name = db.scalar(select(ProductCategory.name).where(ProductCategory.id == row.category_id))
    location_name = None
    if row.primary_location_id is not None:
        location_name = db.scalar(select(Location.name).where(Location.id == row.primary_location_id))
    return AdminCatalogReorderProductOut(
        product_id=row.id,
        title=row.title,
        category_name=category_name,
        stock_global_quantity=int(row.stock_global_quantity or 0),
        reserve_stock=int(row.reserve_stock or 0),
        reorder_status=row.reorder_status,
        reorder_status_updated_at=row.reorder_status_updated_at,
        primary_location_id=row.primary_location_id,
        primary_location_name=location_name,
    )


@router.get("/config/catalog/transfers", response_model=list[AdminCatalogStockTransferOut])
def list_admin_catalog_stock_transfers(
    status_filter: ProductTransferStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminCatalogStockTransferOut]:
    stmt = select(ProductStockTransfer)
    if status_filter is not None:
        stmt = stmt.where(ProductStockTransfer.status == status_filter)
    rows = db.scalars(stmt.order_by(ProductStockTransfer.created_at.desc())).all()

    product_title_by_id = {product_id: title for product_id, title in db.execute(select(CatalogProduct.id, CatalogProduct.title)).all()}
    location_name_by_id = _location_name_map(db)
    user_name_by_id = _user_name_map(
        db,
        [
            value
            for row in rows
            for value in [row.assigned_to_user_id, row.requested_by_user_id, row.completed_by_user_id]
            if value is not None
        ],
    )
    return [
        _transfer_out(
            row,
            product_title_by_id=product_title_by_id,
            location_name_by_id=location_name_by_id,
            user_name_by_id=user_name_by_id,
        )
        for row in rows
    ]


@router.post("/config/catalog/transfers", response_model=AdminCatalogStockTransferOut, status_code=status.HTTP_201_CREATED)
def create_admin_catalog_stock_transfer(
    payload: AdminCatalogStockTransferCreateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogStockTransferOut:
    product = _require_product(db, payload.product_id)
    if product.is_virtual:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Virtual products have no stock transfer")
    _require_location(db, payload.source_location_id)
    _require_location(db, payload.target_location_id)
    if payload.assigned_to_user_id is not None:
        assigned = db.scalar(select(User.id).where(User.id == payload.assigned_to_user_id))
        if assigned is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found")
    try:
        transfer = create_stock_transfer(
            db,
            product_id=payload.product_id,
            source_location_id=payload.source_location_id,
            target_location_id=payload.target_location_id,
            quantity=payload.quantity,
            planned_transfer_date=payload.planned_transfer_date,
            assigned_to_user_id=payload.assigned_to_user_id,
            requested_by_user_id=actor.id,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    db.commit()
    db.refresh(transfer)
    product_title = db.scalar(select(CatalogProduct.title).where(CatalogProduct.id == transfer.product_id)) or "Produit"
    location_name_by_id = _location_name_map(db)
    user_name_by_id = _user_name_map(
        db,
        [value for value in [transfer.assigned_to_user_id, transfer.requested_by_user_id, transfer.completed_by_user_id] if value is not None],
    )
    return _transfer_out(
        transfer,
        product_title_by_id={transfer.product_id: product_title},
        location_name_by_id=location_name_by_id,
        user_name_by_id=user_name_by_id,
    )


@router.post("/config/catalog/transfers/{transfer_id}/complete", response_model=AdminCatalogStockTransferOut)
def complete_admin_catalog_stock_transfer(
    transfer_id: UUID,
    payload: AdminCatalogStockTransferCompleteRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogStockTransferOut:
    transfer = db.scalar(select(ProductStockTransfer).where(ProductStockTransfer.id == transfer_id).with_for_update())
    if transfer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")
    if transfer.status != ProductTransferStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transfer is not pending")

    mark_stock_transfer_done(
        db,
        transfer=transfer,
        completed_by_user_id=actor.id,
        completed_transfer_date=payload.completed_transfer_date,
        note=payload.note,
    )
    db.commit()
    db.refresh(transfer)

    product_title = db.scalar(select(CatalogProduct.title).where(CatalogProduct.id == transfer.product_id)) or "Produit"
    location_name_by_id = _location_name_map(db)
    user_name_by_id = _user_name_map(
        db,
        [value for value in [transfer.assigned_to_user_id, transfer.requested_by_user_id, transfer.completed_by_user_id] if value is not None],
    )
    return _transfer_out(
        transfer,
        product_title_by_id={transfer.product_id: product_title},
        location_name_by_id=location_name_by_id,
        user_name_by_id=user_name_by_id,
    )


@router.post("/config/catalog/transfers/{transfer_id}/cancel", response_model=AdminCatalogStockTransferOut)
def cancel_admin_catalog_stock_transfer(
    transfer_id: UUID,
    payload: AdminCatalogStockTransferCancelRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogStockTransferOut:
    transfer = db.scalar(select(ProductStockTransfer).where(ProductStockTransfer.id == transfer_id).with_for_update())
    if transfer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")
    if transfer.status != ProductTransferStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transfer is not pending")

    cancel_stock_transfer(db, transfer=transfer, note=payload.note)
    db.commit()
    db.refresh(transfer)

    product_title = db.scalar(select(CatalogProduct.title).where(CatalogProduct.id == transfer.product_id)) or "Produit"
    location_name_by_id = _location_name_map(db)
    user_name_by_id = _user_name_map(
        db,
        [value for value in [transfer.assigned_to_user_id, transfer.requested_by_user_id, transfer.completed_by_user_id] if value is not None],
    )
    return _transfer_out(
        transfer,
        product_title_by_id={transfer.product_id: product_title},
        location_name_by_id=location_name_by_id,
        user_name_by_id=user_name_by_id,
    )


@router.get("/catalog/requests", response_model=list[AdminCatalogRequestOut])
def list_admin_catalog_requests(
    status_filter: ProductRequestStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AdminCatalogRequestOut]:
    stmt = select(ProductRequest)
    if status_filter is not None:
        stmt = stmt.where(ProductRequest.status == status_filter)
    rows = db.scalars(stmt.order_by(ProductRequest.requested_at.desc())).all()
    return [_request_out(db, row) for row in rows]


@router.post("/catalog/requests", response_model=AdminCatalogRequestOut, status_code=status.HTTP_201_CREATED)
def create_admin_catalog_request(
    payload: AdminCatalogRequestCreateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogRequestOut:
    _require_student_client(db, payload.student_user_id)
    _require_product(db, payload.product_id)
    _require_location(db, payload.location_id)

    now = utcnow()
    row = ProductRequest(
        student_user_id=payload.student_user_id,
        product_id=payload.product_id,
        location_id=payload.location_id,
        quantity=payload.quantity,
        requested_by_user_id=actor.id,
        request_source=ProductRequestSource.ADMIN,
        status=ProductRequestStatus.PROCESSING,
        requested_at=now,
        note=normalize_optional(payload.note),
        updated_at=now,
    )
    db.add(row)
    db.flush()

    apply_request_acceptance(
        db,
        request_row=row,
        actor_user_id=actor.id,
        should_bill=payload.should_bill,
        note=payload.note,
    )

    db.commit()
    db.refresh(row)
    return _request_out(db, row)


@router.post("/catalog/requests/{request_id}/review", response_model=AdminCatalogRequestOut)
def review_admin_catalog_request(
    request_id: UUID,
    payload: AdminCatalogRequestReviewRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogRequestOut:
    row = db.scalar(select(ProductRequest).where(ProductRequest.id == request_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if row.status != ProductRequestStatus.PROCESSING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request has already been reviewed")

    if payload.accept:
        apply_request_acceptance(
            db,
            request_row=row,
            actor_user_id=actor.id,
            should_bill=payload.should_bill,
            note=payload.note,
        )
    else:
        mark_request_rejected(request_row=row, actor_user_id=actor.id, note=payload.note)

    db.add(row)
    db.commit()
    db.refresh(row)
    return _request_out(db, row)


@router.post("/catalog/requests/{request_id}/deliver", response_model=AdminCatalogRequestOut)
def deliver_admin_catalog_request(
    request_id: UUID,
    payload: AdminCatalogRequestDeliverRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.ADMIN)),
) -> AdminCatalogRequestOut:
    row = db.scalar(select(ProductRequest).where(ProductRequest.id == request_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if row.status not in {ProductRequestStatus.TO_DELIVER, ProductRequestStatus.INVOICE_TO_SEND}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request cannot be marked as delivered")

    delivered_by_user_id = payload.delivered_by_user_id
    if delivered_by_user_id is not None:
        delivered_user = db.scalar(select(User).where(User.id == delivered_by_user_id))
        if delivered_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivered-by user not found")

    mark_request_delivered(
        db,
        request_row=row,
        marker_user_id=actor.id,
        delivered_by_user_id=delivered_by_user_id,
        note=payload.note,
    )
    db.commit()
    db.refresh(row)
    return _request_out(db, row)
