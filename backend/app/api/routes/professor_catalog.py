from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Booking, BookingStatus, CourseSession, Location
from app.models.catalog import Professor as ProfessorModel
from app.models.product_catalog import CatalogProduct, ProductCategory, ProductLocationStock, ProductRequest, ProductRequestSource, ProductRequestStatus
from app.models.user import User, UserRole
from app.schemas.catalog_admin import (
    AdminCatalogProductOut,
    AdminCatalogRequestOut,
    ProfessorCatalogRequestCreateRequest,
    ProfessorCatalogRequestDeliverRequest,
    ProfessorCatalogStudentOut,
)
from app.services.product_catalog import mark_request_delivered, normalize_optional, utcnow

router = APIRouter()


def _resolve_professor_profile(db: Session, *, current_user: User) -> ProfessorModel:
    professor = db.scalar(select(ProfessorModel).where(ProfessorModel.email == current_user.email))
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor profile not found")
    return professor


def _student_ids_for_professor(db: Session, *, professor_id: UUID) -> set[UUID]:
    rows = db.scalars(
        select(distinct(Booking.user_id))
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            CourseSession.professor_id == professor_id,
            Booking.status != BookingStatus.CANCELLED,
        )
    ).all()
    return {value for value in rows if value is not None}


def _display_name(user: User | None) -> str:
    if user is None:
        return "Client"
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    composed = f"{first} {last}".strip()
    return composed or user.email


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
    student = users.get(row.student_user_id)
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == row.product_id))

    location = db.scalar(select(Location).where(Location.id == row.location_id))
    location_name = location.name if location is not None else "Lieu"

    stock = db.scalar(
        select(ProductLocationStock).where(
            ProductLocationStock.product_id == row.product_id,
            ProductLocationStock.location_id == row.location_id,
        )
    )

    return AdminCatalogRequestOut(
        id=row.id,
        student_user_id=row.student_user_id,
        student_name=_display_name(student),
        product_id=row.product_id,
        product_title=product.title if product is not None else "Produit",
        location_id=row.location_id,
        location_name=location_name,
        quantity=int(row.quantity or 0),
        requested_by_user_id=row.requested_by_user_id,
        requested_by_name=_display_name(users.get(row.requested_by_user_id)) if row.requested_by_user_id else None,
        request_source=row.request_source,
        status=row.status,
        requested_at=row.requested_at,
        admin_reviewed_by_user_id=row.admin_reviewed_by_user_id,
        admin_reviewed_by_name=_display_name(users.get(row.admin_reviewed_by_user_id)) if row.admin_reviewed_by_user_id else None,
        admin_reviewed_at=row.admin_reviewed_at,
        accepted=row.accepted,
        should_bill=row.should_bill,
        manual_transaction_id=row.manual_transaction_id,
        delivered_by_user_id=row.delivered_by_user_id,
        delivered_by_name=_display_name(users.get(row.delivered_by_user_id)) if row.delivered_by_user_id else None,
        delivery_marked_by_user_id=row.delivery_marked_by_user_id,
        delivery_marked_by_name=_display_name(users.get(row.delivery_marked_by_user_id)) if row.delivery_marked_by_user_id else None,
        delivery_marked_at=row.delivery_marked_at,
        note=row.note,
        stock_real_quantity=(int(stock.real_quantity) if stock is not None else None),
        stock_estimated_quantity=(int(stock.estimated_quantity) if stock is not None else None),
    )


@router.get("/professors/me/catalog/products", response_model=list[AdminCatalogProductOut])
def list_professor_catalog_products(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.PROF)),
) -> list[AdminCatalogProductOut]:
    category_rows = db.execute(select(ProductCategory.id, ProductCategory.name)).all()
    category_name_by_id = {category_id: name for category_id, name in category_rows}
    location_name_by_id = {location_id: name for location_id, name in db.execute(select(Location.id, Location.name)).all()}

    stmt = select(CatalogProduct)
    if not include_inactive:
        stmt = stmt.where(CatalogProduct.active.is_(True))
    rows = db.scalars(stmt.order_by(CatalogProduct.title.asc())).all()

    return [
        AdminCatalogProductOut(
            id=row.id,
            category_id=row.category_id,
            category_name=category_name_by_id.get(row.category_id) if row.category_id else None,
            primary_location_id=row.primary_location_id,
            primary_location_name=location_name_by_id.get(row.primary_location_id) if row.primary_location_id else None,
            title=row.title,
            barcode=row.barcode,
            price_excl_vat=row.price_excl_vat,
            price_incl_vat=row.price_incl_vat,
            vat_rate=row.vat_rate,
            stock_global_quantity=int(row.stock_global_quantity or 0),
            reserve_stock=int(row.reserve_stock or 0),
            reorder_status=row.reorder_status,
            reorder_status_updated_at=row.reorder_status_updated_at,
            image_url=row.image_url,
            short_description=row.short_description,
            long_description=row.long_description,
            web_link=row.web_link,
            purchasable_online=bool(row.purchasable_online),
            is_public=bool(row.is_public),
            active=bool(row.active),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/professors/me/catalog/students", response_model=list[ProfessorCatalogStudentOut])
def list_professor_catalog_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorCatalogStudentOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    student_ids = _student_ids_for_professor(db, professor_id=professor.id)
    if not student_ids:
        return []
    students = db.scalars(select(User).where(User.id.in_(student_ids)).order_by(User.last_name.asc(), User.first_name.asc())).all()
    return [ProfessorCatalogStudentOut(user_id=row.id, display_name=_display_name(row)) for row in students]


@router.post("/professors/me/catalog/requests", response_model=AdminCatalogRequestOut, status_code=status.HTTP_201_CREATED)
def create_professor_catalog_request(
    payload: ProfessorCatalogRequestCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> AdminCatalogRequestOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    student_ids = _student_ids_for_professor(db, professor_id=professor.id)
    if payload.student_user_id not in student_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Student is not linked to this professor")

    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == payload.product_id, CatalogProduct.active.is_(True)))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    location_exists = db.scalar(select(Location.id).where(Location.id == payload.location_id))
    if location_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

    now = utcnow()
    row = ProductRequest(
        student_user_id=payload.student_user_id,
        product_id=payload.product_id,
        location_id=payload.location_id,
        quantity=payload.quantity,
        requested_by_user_id=current_user.id,
        request_source=ProductRequestSource.PROFESSOR,
        status=ProductRequestStatus.PROCESSING,
        requested_at=now,
        note=normalize_optional(payload.note),
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _request_out(db, row)


@router.get("/professors/me/catalog/requests", response_model=list[AdminCatalogRequestOut])
def list_professor_catalog_requests(
    only_to_deliver: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[AdminCatalogRequestOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    student_ids = _student_ids_for_professor(db, professor_id=professor.id)
    if not student_ids:
        return []

    stmt = select(ProductRequest).where(ProductRequest.student_user_id.in_(student_ids))
    if only_to_deliver:
        stmt = stmt.where(ProductRequest.status.in_([ProductRequestStatus.TO_DELIVER, ProductRequestStatus.INVOICE_TO_SEND]))
    rows = db.scalars(stmt.order_by(ProductRequest.requested_at.desc())).all()
    return [_request_out(db, row) for row in rows]


@router.post("/professors/me/catalog/requests/{request_id}/deliver", response_model=AdminCatalogRequestOut)
def mark_professor_catalog_request_delivered(
    request_id: UUID,
    payload: ProfessorCatalogRequestDeliverRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> AdminCatalogRequestOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    student_ids = _student_ids_for_professor(db, professor_id=professor.id)

    row = db.scalar(select(ProductRequest).where(ProductRequest.id == request_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if row.student_user_id not in student_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request is not assigned to this professor")
    if row.status not in {ProductRequestStatus.TO_DELIVER, ProductRequestStatus.INVOICE_TO_SEND}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request cannot be marked as delivered")

    mark_request_delivered(
        db,
        request_row=row,
        marker_user_id=current_user.id,
        delivered_by_user_id=payload.delivered_by_user_id,
        note=payload.note,
    )
    db.commit()
    db.refresh(row)
    return _request_out(db, row)
