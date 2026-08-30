from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Location
from app.models.supply_order import ProductSupplyOrder, ProductSupplyOrderLine
from app.models.user import User, UserRole
from app.schemas.supply_order import SupplyOrderCreate, SupplyOrderItemOut, SupplyOrderOut, SupplyOrderReceive
from app.services.supply_orders import complete_supply_order, create_supply_order, order_lines

router = APIRouter(prefix="/admin/config/catalog/supply-orders")


def as_output(db: Session, row: ProductSupplyOrder) -> SupplyOrderOut:
    return SupplyOrderOut(
        **{key: getattr(row, key) for key in ("id", "reference", "supplier", "location_id", "ordered_date",
           "expected_delivery_date", "status", "note", "received_date", "created_at", "completed_at")},
        location_name=db.scalar(select(Location.name).where(Location.id == row.location_id)) or "",
        items=[SupplyOrderItemOut.model_validate(line) for line in order_lines(db, row.id)],
    )


@router.get("", response_model=list[SupplyOrderOut])
def list_orders(db: Session = Depends(get_db), _: User = Depends(require_roles(UserRole.ADMIN)),
                limit: int = Query(default=100, ge=1, le=500)):
    rows = db.scalars(select(ProductSupplyOrder).order_by(
        (ProductSupplyOrder.status == "ORDERED").desc(), ProductSupplyOrder.created_at.desc(),
    ).limit(limit)).all()
    # Load relations in bulk so history does not add one query per line/order.
    locations = dict(db.execute(select(Location.id, Location.name)).all())
    lines_by_order: dict = {}
    if rows:
        for line in db.scalars(select(ProductSupplyOrderLine).where(ProductSupplyOrderLine.order_id.in_([r.id for r in rows]))):
            lines_by_order.setdefault(line.order_id, []).append(SupplyOrderItemOut.model_validate(line))
    return [SupplyOrderOut(
        **{key: getattr(row, key) for key in ("id", "reference", "supplier", "location_id", "ordered_date",
           "expected_delivery_date", "status", "note", "received_date", "created_at", "completed_at")},
        location_name=locations.get(row.location_id, ""), items=lines_by_order.get(row.id, []),
    ) for row in rows]


@router.post("", response_model=SupplyOrderOut)
def create_order(payload: SupplyOrderCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(UserRole.ADMIN))):
    try:
        row = create_supply_order(db, payload, actor.id)
        db.commit()
        return as_output(db, row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@router.post("/{order_id}/receive", response_model=SupplyOrderOut)
def receive_order(order_id: UUID, payload: SupplyOrderReceive, db: Session = Depends(get_db), actor: User = Depends(require_roles(UserRole.ADMIN))):
    try:
        row = complete_supply_order(db, order_id, actor_id=actor.id, received_date=payload.received_date, product_links=payload.product_links)
        db.commit()
        return as_output(db, row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@router.post("/{order_id}/cancel", response_model=SupplyOrderOut)
def cancel_order(order_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_roles(UserRole.ADMIN))):
    try:
        row = complete_supply_order(db, order_id, actor_id=actor.id, cancel=True)
        db.commit()
        return as_output(db, row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
