from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.catalog import Location
from app.models.product_catalog import CatalogProduct, ProductReorderStatus, StockMovementSourceType, StockMovementType
from app.models.supply_order import ProductSupplyOrder, ProductSupplyOrderLine
from app.schemas.supply_order import SupplyOrderCreate
from app.services.product_catalog import PARIS_TIMEZONE, create_stock_movement, normalize_optional, utcnow


def order_lines(db: Session, order_id: UUID) -> list[ProductSupplyOrderLine]:
    return list(db.scalars(select(ProductSupplyOrderLine).where(ProductSupplyOrderLine.order_id == order_id)
                           .order_by(ProductSupplyOrderLine.product_id)).all())


def create_supply_order(db: Session, payload: SupplyOrderCreate, actor_id: UUID | None) -> ProductSupplyOrder:
    # Serialize retries for the same submission, including before the row exists.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"supply-order:{payload.submission_id}"})
    existing = db.get(ProductSupplyOrder, payload.submission_id)
    if existing:
        same_header = all(getattr(existing, key) == value for key, value in {
            "location_id": payload.location_id, "ordered_date": payload.ordered_date,
            "expected_delivery_date": payload.expected_delivery_date, "reference": normalize_optional(payload.reference),
            "supplier": normalize_optional(payload.supplier), "note": normalize_optional(payload.note),
        }.items())
        same_lines = {(str(line.product_id) if line.product_id else line.product_title.strip().casefold()): line.quantity for line in order_lines(db, existing.id)} == {
            (str(item.product_id) if item.product_id else (item.product_title or "").strip().casefold()): item.quantity for item in payload.items
        }
        if not same_header or not same_lines:
            raise ValueError("Cette saisie a déjà été enregistrée avec un contenu différent. Rechargez la page.")
        return existing
    location = db.get(Location, payload.location_id)
    if not location or not location.active or location.is_online:
        raise ValueError("Choisissez un lieu de livraison physique actif.")
    if payload.ordered_date > utcnow().astimezone(PARIS_TIMEZONE).date():
        raise ValueError("La date de commande ne peut pas être dans le futur.")
    product_ids = [item.product_id for item in payload.items if item.product_id]
    products = list(db.scalars(select(CatalogProduct).where(CatalogProduct.id.in_(product_ids))
                              .order_by(CatalogProduct.id).with_for_update()).all())
    if len(products) != len(product_ids) or any(not p.active or p.is_virtual or p.nature.value != "material" for p in products):
        raise ValueError("La commande ne peut contenir que des produits matériels actifs.")
    by_id = {p.id: p for p in products}
    row = ProductSupplyOrder(
        id=payload.submission_id, location_id=payload.location_id, reference=normalize_optional(payload.reference),
        supplier=normalize_optional(payload.supplier), ordered_date=payload.ordered_date,
        expected_delivery_date=payload.expected_delivery_date, note=normalize_optional(payload.note),
        status="ORDERED", created_by=actor_id,
    )
    db.add(row)
    db.flush()
    for item in payload.items:
        product = by_id.get(item.product_id)
        db.add(ProductSupplyOrderLine(order_id=row.id, product_id=product.id if product else None,
                                      product_title=product.title if product else item.product_title.strip(), quantity=item.quantity))
        if product:
            product.reorder_status = ProductReorderStatus.ORDERED
            product.reorder_status_updated_at = utcnow()
            product.updated_at = utcnow()
    db.flush()
    return row


def complete_supply_order(
    db: Session, order_id: UUID, *, actor_id: UUID | None, received_date: date | None = None, cancel: bool = False,
    product_links: dict[UUID, UUID] | None = None,
) -> ProductSupplyOrder:
    row = db.scalar(select(ProductSupplyOrder).where(ProductSupplyOrder.id == order_id).with_for_update())
    if row is None:
        raise ValueError("Commande introuvable.")
    target_status = "CANCELLED" if cancel else "RECEIVED"
    if row.status == target_status:
        return row
    if row.status != "ORDERED":
        raise ValueError("Cette commande est déjà clôturée : aucune modification de stock effectuée.")
    now = utcnow()
    if not cancel and (received_date is None or received_date > now.astimezone(PARIS_TIMEZONE).date() or received_date < row.ordered_date):
        raise ValueError("La date de réception doit être comprise entre la commande et aujourd’hui.")
    lines = order_lines(db, row.id)
    resolved_ids = {line.id: line.product_id or (product_links or {}).get(line.id) for line in lines}
    if not cancel and any(value is None for value in resolved_ids.values()):
        raise ValueError("Rattachez chaque produit non référencé à une fiche du catalogue avant réception.")
    nonempty_ids = [value for value in resolved_ids.values() if value]
    if len(nonempty_ids) != len(set(nonempty_ids)):
        raise ValueError("Deux lignes ne peuvent pas être rattachées au même produit.")
    products = list(db.scalars(select(CatalogProduct).where(CatalogProduct.id.in_(nonempty_ids))
                              .order_by(CatalogProduct.id).with_for_update()).all())
    if not cancel and (len(products) != len(nonempty_ids) or any(p.is_virtual or p.nature.value != "material" for p in products)):
        raise ValueError("Un produit n’est plus stockable ; vérifiez le catalogue avant réception.")
    if not cancel:
        for line in lines:
            line.product_id = resolved_ids[line.id]
    row.status = target_status
    row.completed_by = actor_id
    row.completed_at = now
    row.received_date = None if cancel else received_date
    db.flush()
    if not cancel:
        for line in lines:
            movement = create_stock_movement(
                db, product_id=line.product_id, location_id=row.location_id,
                movement_type=StockMovementType.STOCK_IN, quantity=Decimal(line.quantity),
                source_type=StockMovementSourceType.PURCHASE,
                source_reference=row.reference or f"Commande {str(row.id)[:8]}",
                note=f"Réception intégrale de la commande fournisseur {row.id}", attachment_key=None,
                created_by=actor_id, occurred_at=datetime.combine(received_date, time(12), tzinfo=PARIS_TIMEZONE),
                meta={"supply_order_id": str(row.id), "supply_order_line_id": str(line.id)},
            )
            line.stock_movement_id = movement.id
    # Keep 'ordered' if another delivery of the same product is still outstanding.
    pending_ids = set(db.scalars(select(ProductSupplyOrderLine.product_id).join(
        ProductSupplyOrder, ProductSupplyOrder.id == ProductSupplyOrderLine.order_id,
    ).where(ProductSupplyOrder.status == "ORDERED", ProductSupplyOrderLine.product_id.in_([p.id for p in products]))).all())
    for product in products:
        product.reorder_status = (
            ProductReorderStatus.ORDERED if product.id in pending_ids else
            ProductReorderStatus.TO_ORDER if product.stock_global_quantity < product.reserve_stock else
            ProductReorderStatus.NORMAL if cancel else ProductReorderStatus.RECEIVED
        )
        product.reorder_status_updated_at = now
        product.updated_at = now
    db.flush()
    return row
