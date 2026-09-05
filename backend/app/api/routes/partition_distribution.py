from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import get_db, require_roles
from app.models.catalog import Booking, BookingStatus, CourseSession, Location, Professor, SessionStatus
from app.models.partition_distribution import PartitionMovement
from app.models.product_catalog import CatalogProduct, ProductLocationStock, ProductRequest, ProductRequestStatus
from app.models.repertoire import StudentSheetMusic
from app.models.user import User, UserRole
from app.services.partition_distribution import confirm_movement, held_quantity, lock_custody, richelieu

router = APIRouter()
PARIS = ZoneInfo("Europe/Paris")
DELIVERY_BOOKINGS = (BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW)


def is_paris(location):
    name = location.name.casefold()
    return any(word in name for word in ("richelieu", "pompe", "scheffer", "assas"))


def actor_professor(db, actor):
    professor = db.scalar(select(Professor).where(func.lower(Professor.email) == actor.email.lower()))
    if professor is None:
        raise HTTPException(403, "Profil professeur introuvable.")
    return professor


def weekly_students(db, week):
    start = datetime.combine(week, time.min, PARIS)
    rows = db.execute(select(Booking.user_id, CourseSession, Location, User)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(Location, Location.id == CourseSession.location_id).join(User, User.id == Booking.user_id)
        .where(Booking.status.in_(DELIVERY_BOOKINGS), CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.start_at_utc >= start, CourseSession.start_at_utc < start + timedelta(days=7))
        .order_by(CourseSession.start_at_utc, CourseSession.id)).all()
    students = {}
    for student_id, session, location, user in rows:
        professor_id = session.substitute_teacher_id or session.professor_id
        if not is_paris(location) or professor_id is None:
            continue
        students.setdefault(student_id, dict(student_id=str(student_id), student_name=f"{user.first_name or ''} {user.last_name or ''}".strip(),
            professor_id=str(professor_id), session_id=str(session.id), site=location.name,
            course_at=session.start_at_utc.isoformat()))
    return students


@router.get("/partition-distribution")
def dashboard(week: date | None = None, db=Depends(get_db), actor=Depends(require_roles(UserRole.ADMIN, UserRole.PROF))):
    today = datetime.now(PARIS).date()
    week = week or (today + timedelta(days=2) if today.weekday() >= 5 else today)
    week -= timedelta(days=week.weekday())
    own = actor_professor(db, actor).id if actor.role == UserRole.PROF else None
    students = weekly_students(db, week)
    assignments = list(db.scalars(select(StudentSheetMusic).where(StudentSheetMusic.student_id.in_(students))).all()) if students else []
    by_student = defaultdict(list)
    for row in assignments:
        by_student[row.student_id].append(row)
    needs = []
    already_delivered = set(db.execute(select(ProductRequest.student_user_id, ProductRequest.product_id).where(
        ProductRequest.student_user_id.in_(students), ProductRequest.status == ProductRequestStatus.DELIVERED)).all()) if students else set()
    for student_id, item in students.items():
        if own and item["professor_id"] != str(own):
            continue
        rows = by_student[student_id]
        delivered = {r.product_id for r in rows if r.delivered_at or r.status in {"DELIVERED", "IN_PROGRESS", "COMPLETED"}}
        delivered.update(product for student, product in already_delivered if student == student_id)
        pending = sorted((r for r in rows if r.status in {"STANDBY", "TO_DELIVER"} and not r.delivered_at), key=lambda r: (r.created_at, str(r.id)))
        seen = set(delivered)
        for row in pending:
            if row.product_id in seen:
                continue
            seen.add(row.product_id)
            needs.append({**item, "assignment_id": str(row.id), "product_id": str(row.product_id) if row.product_id else None,
                          "title": row.title_snapshot, "status": "À remettre"})
        if not rows and not delivered:
            needs.append({**item, "assignment_id": None, "product_id": None, "title": "À définir", "status": "À définir"})
    professors = {str(p.id): f"{p.first_name} {p.last_name}" for p in db.scalars(select(Professor)).all()}
    from app.api.routes.repertoire import _partition_products
    products = _partition_products(db)
    source = richelieu(db)
    from app.services.product_catalog import _available_physical_quantity
    stocks = {s.product_id: _available_physical_quantity(db, stock=s) for s in db.scalars(select(ProductLocationStock).where(ProductLocationStock.location_id == source.id)).all()}
    stmt = select(PartitionMovement)
    if own:
        stmt = stmt.where(PartitionMovement.professor_id == own)
    movements = list(db.scalars(stmt.order_by(PartitionMovement.created_at.desc())).all())
    actor_ids = {m.actor_user_id for m in movements} | {m.confirmed_by_user_id for m in movements if m.confirmed_by_user_id}
    actor_names = {u.id: f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email
        for u in db.scalars(select(User).where(User.id.in_(actor_ids))).all()}
    assignment_ids = {m.assignment_id for m in movements if m.assignment_id}
    delivery_students = {assignment_id: f"{first or ''} {last or ''}".strip()
        for assignment_id, first, last in db.execute(select(StudentSheetMusic.id, User.first_name, User.last_name)
            .join(User, User.id == StudentSheetMusic.student_id).where(StudentSheetMusic.id.in_(assignment_ids))).all()}
    balances = defaultdict(int)
    for m in movements:
        if m.state == "CONFIRMED":
            balances[(str(m.professor_id), str(m.product_id))] += m.quantity if m.kind == "PICKUP" else -m.quantity
    summary_keys = {(n["professor_id"], n["product_id"]) for n in needs if n["product_id"]}
    summary_keys.update((str(m.professor_id), str(m.product_id)) for m in movements)
    titles = {str(p.id): p.title for p in products}
    totals = []
    for prof, product in sorted(summary_keys):
        need = sum(1 for n in needs if n["professor_id"] == prof and n["product_id"] == product)
        held = balances[(prof, product)]
        pending = sum(m.quantity for m in movements if str(m.professor_id) == prof and str(m.product_id) == product and m.state == "PENDING" and m.kind == "PICKUP")
        totals.append(dict(professor_id=prof, professor=professors.get(prof, "Professeur"), product_id=product,
            title=titles.get(product, "Partition archivée"), needed=need, held=held, pending=pending,
            to_pickup=max(0, need-held-pending), richelieu=stocks.get(UUID(product), 0)))
    for n in needs:
        n["professor"] = professors.get(n["professor_id"], "Professeur")
    return dict(week=week.isoformat(), is_admin=own is None, needs=needs, totals=totals,
        products=[dict(id=str(p.id), title=p.title) for p in products],
        movements=[dict(id=str(m.id), professor=professors.get(str(m.professor_id), "Professeur"), title=titles.get(str(m.product_id), "Partition"),
            professor_id=str(m.professor_id), product_id=str(m.product_id),
            kind=m.kind, state=m.state, quantity=m.quantity, created_at=m.created_at.isoformat(),
            confirmed_at=m.confirmed_at.isoformat() if m.confirmed_at else None,
            student=delivery_students.get(m.assignment_id), actor=actor_names.get(m.actor_user_id),
            confirmed_by=actor_names.get(m.confirmed_by_user_id),
            actor_user_id=str(m.actor_user_id), confirmed_by_user_id=str(m.confirmed_by_user_id) if m.confirmed_by_user_id else None) for i, m in enumerate(movements) if i < 200 or m.state == "PENDING"])


class MovementIn(BaseModel):
    operation_id: UUID
    professor_id: UUID
    product_id: UUID
    quantity: int = Field(ge=1, le=500)
    kind: str


@router.post("/partition-distribution/movements")
def request_movement(payload: MovementIn, db=Depends(get_db), actor=Depends(require_roles(UserRole.ADMIN, UserRole.PROF))):
    if actor.role == UserRole.PROF and actor_professor(db, actor).id != payload.professor_id:
        raise HTTPException(403, "Accès refusé.")
    if payload.kind not in {"PICKUP", "RETURN"}:
        raise HTTPException(422, "Mouvement invalide.")
    from app.api.routes.repertoire import _partition_product
    product = db.get(CatalogProduct, payload.product_id) if payload.kind == "RETURN" else _partition_product(db, payload.product_id)
    if product is None or product.is_virtual:
        raise HTTPException(422, "Partition invalide.")
    lock_custody(db, payload.professor_id, payload.product_id)
    existing = db.scalar(select(PartitionMovement).where(PartitionMovement.operation_id == payload.operation_id))
    if existing:
        if (existing.professor_id, existing.product_id, existing.quantity, existing.kind) != (payload.professor_id, payload.product_id, payload.quantity, payload.kind):
            raise HTTPException(409, "Cette opération a déjà été utilisée.")
        return {"id": str(existing.id), "state": existing.state}
    pending = db.scalar(select(PartitionMovement).where(PartitionMovement.professor_id == payload.professor_id,
        PartitionMovement.product_id == payload.product_id, PartitionMovement.kind == payload.kind, PartitionMovement.state == "PENDING"))
    if pending:
        raise HTTPException(409, "Une demande est déjà en attente pour cette partition.")
    if payload.kind == "RETURN" and held_quantity(db, payload.professor_id, payload.product_id) < payload.quantity:
        raise HTTPException(409, "Quantité détenue insuffisante.")
    row = PartitionMovement(**payload.model_dump(), location_id=richelieu(db).id, actor_user_id=actor.id, state="PENDING")
    db.add(row)
    db.flush()
    db.commit()
    return {"id": str(row.id), "state": row.state}


class ConfirmIn(BaseModel):
    quantity: int = Field(ge=1, le=500)


@router.post("/partition-distribution/movements/{movement_id}/confirm")
def confirm(movement_id: UUID, payload: ConfirmIn, db=Depends(get_db), actor=Depends(require_roles(UserRole.ADMIN, UserRole.PROF))):
    row = db.scalar(select(PartitionMovement).where(PartitionMovement.id == movement_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Demande introuvable.")
    if actor.role == UserRole.PROF and (row.professor_id != actor_professor(db, actor).id or row.kind != "PICKUP"):
        raise HTTPException(403, "Vous pouvez confirmer uniquement votre propre retrait.")
    if row.state != "CONFIRMED":
        row.quantity = payload.quantity
        confirm_movement(db, row, actor.id)
        db.commit()
    return {"state": row.state}


class DeliveryIn(BaseModel):
    assignment_id: UUID
    professor_id: UUID
    product_id: UUID


@router.post("/partition-distribution/movements/{movement_id}/cancel")
def cancel(movement_id: UUID, db=Depends(get_db), actor=Depends(require_roles(UserRole.ADMIN, UserRole.PROF))):
    row = db.scalar(select(PartitionMovement).where(PartitionMovement.id == movement_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Demande introuvable.")
    if actor.role == UserRole.PROF and actor_professor(db, actor).id != row.professor_id:
        raise HTTPException(403, "Accès refusé.")
    if row.state == "CONFIRMED":
        raise HTTPException(409, "Le mouvement est déjà confirmé. Déclarez un retour si nécessaire.")
    row.state = "CANCELLED"
    row.confirmed_by_user_id = actor.id
    row.confirmed_at = datetime.now(PARIS)
    db.commit()
    return {"state": row.state}


@router.post("/partition-distribution/deliver")
def deliver(payload: DeliveryIn, db=Depends(get_db), actor=Depends(require_roles(UserRole.ADMIN, UserRole.PROF))):
    if actor.role == UserRole.PROF and actor_professor(db, actor).id != payload.professor_id:
        raise HTTPException(403, "Accès refusé.")
    row = db.scalar(select(StudentSheetMusic).where(StudentSheetMusic.id == payload.assignment_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Partition introuvable.")
    from app.services.partition_distribution import delivery_professor
    if delivery_professor(db, row.student_id, payload.professor_id) is None:
        raise HTTPException(409, "Cet élève n'est plus affecté à ce professeur dans le planning Paris.")
    if row.delivered_at:
        if row.product_id != payload.product_id:
            raise HTTPException(409, "Une autre partition a déjà été remise.")
        return {"state": "DELIVERED"}
    from app.api.routes.repertoire import _update_assignment, AssignmentUpdate
    _update_assignment(db, row, AssignmentUpdate(product_id=payload.product_id, status="DELIVERED"), actor,
        allow_product_change=True, distribution_professor_id=payload.professor_id)
    return {"state": "DELIVERED"}
