"""Physical custody ledger. Callers commit stock, delivery and history together."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import case, func, select
from app.models.catalog import Professor, Location
from app.models.partition_distribution import PartitionMovement
from app.models.product_catalog import CatalogProduct, ProductLocationStock
from app.models.repertoire import StudentSheetMusic


def held_expression():
    return case((PartitionMovement.kind == "PICKUP", PartitionMovement.quantity), else_=-PartitionMovement.quantity)


def held_quantity(db, professor_id, product_id):
    return int(db.scalar(select(func.coalesce(func.sum(held_expression()), 0)).where(
        PartitionMovement.professor_id == professor_id, PartitionMovement.product_id == product_id,
        PartitionMovement.state == "CONFIRMED")) or 0)


def richelieu(db):
    rows = list(db.scalars(select(Location).where(func.lower(Location.name).contains("richelieu"))).all())
    if len(rows) != 1:
        raise HTTPException(409, "Le lieu de retrait Richelieu doit être identifié de façon unique.")
    return rows[0]


def lock_custody(db, professor_id, product_id):
    # A stable parent row serializes even the first movement, before a balance exists.
    professor = db.scalar(select(Professor).where(Professor.id == professor_id).with_for_update())
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.id == product_id).with_for_update())
    if professor is None or product is None or product.is_virtual:
        raise HTTPException(422, "Professeur ou partition physique invalide.")


def confirm_movement(db, movement, actor_id):
    if movement.state == "CONFIRMED":
        return
    if movement.state != "PENDING":
        raise HTTPException(409, "Cette demande est annulée.")
    lock_custody(db, movement.professor_id, movement.product_id)
    stock = db.scalar(select(ProductLocationStock).where(
        ProductLocationStock.location_id == movement.location_id,
        ProductLocationStock.product_id == movement.product_id).with_for_update())
    if stock is None:
        raise HTTPException(409, "Inventaire Richelieu à renseigner pour cette partition.")
    if movement.kind == "PICKUP":
        from app.services.product_catalog import _available_physical_quantity
        if _available_physical_quantity(db, stock=stock) < movement.quantity:
            raise HTTPException(409, "Stock disponible insuffisant à Richelieu.")
        delta = -movement.quantity
    elif movement.kind == "RETURN":
        if held_quantity(db, movement.professor_id, movement.product_id) < movement.quantity:
            raise HTTPException(409, "Le professeur ne détient pas cette quantité.")
        delta = movement.quantity
    else:
        raise HTTPException(422, "Mouvement invalide.")
    now = datetime.now(timezone.utc)
    stock.real_quantity += delta
    stock.estimated_quantity += delta
    stock.real_updated_at = stock.estimated_updated_at = stock.updated_at = now
    movement.state = "CONFIRMED"
    movement.confirmed_at = now
    movement.confirmed_by_user_id = actor_id
    db.flush()
    from app.services.product_catalog import recalculate_product_global_stock
    recalculate_product_global_stock(db, product_id=movement.product_id)


def consume_partition(db, row, professor_id, actor_id):
    """One physical handover per assignment; duplicate student/product rows are refused."""
    if row.product_id is None:
        raise HTTPException(422, "Choisissez la partition avant la remise.")
    lock_custody(db, professor_id, row.product_id)
    # Serialize deliveries of different assignments for the same student too.
    from app.models.user import User
    db.scalar(select(User).where(User.id == row.student_id).with_for_update())
    if db.scalar(select(PartitionMovement.id).where(PartitionMovement.assignment_id == row.id)):
        return
    duplicate = db.scalar(select(StudentSheetMusic.id).where(
        StudentSheetMusic.student_id == row.student_id, StudentSheetMusic.product_id == row.product_id,
        StudentSheetMusic.id != row.id, StudentSheetMusic.delivered_at.is_not(None)))
    if duplicate:
        raise HTTPException(409, "Cette partition a déjà été remise à cet élève. Vérifiez son suivi.")
    from app.models.product_catalog import ProductRequest, ProductRequestStatus
    if db.scalar(select(ProductRequest.id).where(ProductRequest.student_user_id == row.student_id,
        ProductRequest.product_id == row.product_id, ProductRequest.status == ProductRequestStatus.DELIVERED)):
        raise HTTPException(409, "Une remise de cette partition est déjà enregistrée dans le catalogue.")
    if held_quantity(db, professor_id, row.product_id) < 1:
        raise HTTPException(409, "Aucun exemplaire détenu : faites valider le retrait à Richelieu dans Mes partitions.")
    now = datetime.now(timezone.utc)
    db.add(PartitionMovement(operation_id=uuid4(), professor_id=professor_id, product_id=row.product_id,
        location_id=richelieu(db).id, assignment_id=row.id, quantity=1, kind="DELIVERY", state="CONFIRMED",
        actor_user_id=actor_id, confirmed_by_user_id=actor_id, confirmed_at=now))
    db.flush()
    from app.services.product_catalog import recalculate_product_global_stock
    recalculate_product_global_stock(db, product_id=row.product_id)


def delivery_professor(db, student_id, preferred=None):
    from app.models.catalog import Booking, CourseSession, SessionStatus
    from app.api.routes.partition_distribution import is_paris, DELIVERY_BOOKINGS
    rows = db.execute(select(CourseSession, Location).join(Location, Location.id == CourseSession.location_id)
        .join(Booking, Booking.session_id == CourseSession.id).where(
            Booking.user_id == student_id, Booking.status.in_(DELIVERY_BOOKINGS),
            CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.start_at_utc >= datetime.now(timezone.utc) - timedelta(days=7))
        .order_by(CourseSession.start_at_utc)).all()
    for session, location in rows:
        professor_id = session.substitute_teacher_id or session.professor_id
        if is_paris(location) and professor_id and (preferred is None or preferred == professor_id):
            return professor_id
    return None
