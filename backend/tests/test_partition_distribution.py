"""Integration checks against an isolated, migrated PostgreSQL database.

Set PARTITION_TEST_DATABASE_URL; each test rolls back its own outer transaction.
"""
import os
from datetime import datetime, time, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, DeliveryMode, Location, Professor
from app.models.product_catalog import CatalogProduct, ProductLocationStock
from app.models.repertoire import StudentSheetMusic
from app.models.user import User, UserRole
from app.api.routes.partition_distribution import (
    ConfirmIn, DeliveryIn, MovementIn, PARIS, cancel, confirm, dashboard, deliver, request_movement,
)
from app.services.partition_distribution import held_quantity


@pytest.fixture
def scenario():
    url = os.getenv("PARTITION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires isolated PARTITION_TEST_DATABASE_URL")
    engine = create_engine(url)
    with engine.connect() as connection:
        outer = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
        suffix = uuid4().hex
        admin = User(email=f"admin-{suffix}@test.invalid", hashed_password="test", role=UserRole.ADMIN)
        actor = User(email=f"prof-{suffix}@test.invalid", hashed_password="test", role=UserRole.PROF)
        student = User(email=f"student-{suffix}@test.invalid", hashed_password="test", first_name="Élève", role=UserRole.CLIENT)
        prof = Professor(email=actor.email, first_name="Prof", last_name=suffix)
        location = db.scalar(select(Location).where(Location.name == "Rue de Richelieu"))
        if location is None:
            location = Location(code=f"R-{suffix}", name="Rue de Richelieu", timezone="Europe/Paris")
        product = CatalogProduct(title=f"Partition degré 6 {suffix}", active=True, is_virtual=False)
        entity = db.scalar(text("SELECT id FROM legal_entities LIMIT 1"))
        course = CourseType(code=suffix, name="Piano", service_code="TEST", duration_minutes=60, mode=DeliveryMode.ONSITE, default_capacity=6,
            seller_legal_entity_id=entity, payor_legal_entity_id=entity)
        db.add_all([admin, actor, student, prof, location, product, course]); db.flush()
        stock = ProductLocationStock(product_id=product.id, location_id=location.id, real_quantity=10, estimated_quantity=10)
        row = StudentSheetMusic(student_id=student.id, product_id=product.id, title_snapshot=product.title, status="TO_DELIVER")
        today = datetime.now(PARIS).date()
        week = today + timedelta(days=7-today.weekday())
        start = datetime.combine(week, time(14), PARIS)
        session = CourseSession(course_type_id=course.id, location_id=location.id, professor_id=prof.id,
            snapshot_seller_legal_entity_id=entity, snapshot_payor_legal_entity_id=entity,
            title="Piano", start_at_utc=start, end_at_utc=start+timedelta(hours=1), capacity_max=6,
            auto_cancel_deadline_utc=start, timezone="Europe/Paris")
        db.add_all([stock,row,session]); db.flush()
        db.add(Booking(session_id=session.id, user_id=student.id, status=BookingStatus.BOOKED)); db.flush()
        try:
            yield db, admin, actor, prof, student, product, stock, row, session, week
        finally:
            db.close(); outer.rollback()
    engine.dispose()


def pickup(db, admin, actor, prof, product, quantity):
    payload = MovementIn(operation_id=uuid4(), professor_id=prof.id, product_id=product.id, quantity=quantity, kind="PICKUP")
    result = request_movement(payload, db, actor)
    confirm(result["id"], ConfirmIn(quantity=quantity), db, admin)
    return payload, result


def test_pickup_delivery_return_and_retries_conserve_stock(scenario):
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    payload, result = pickup(db, admin, actor, prof, product, 5)
    assert stock.real_quantity == 5
    assert held_quantity(db, prof.id, product.id) == 5
    assert product.stock_global_quantity == 10
    assert request_movement(payload, db, actor)["id"] == result["id"]
    confirm(result["id"], ConfirmIn(quantity=5), db, admin)
    assert stock.real_quantity == 5
    args = DeliveryIn(assignment_id=row.id, professor_id=prof.id, product_id=product.id)
    deliver(args, db, actor)
    deliver(args, db, actor)
    assert held_quantity(db, prof.id, product.id) == 4
    assert product.stock_global_quantity == 9
    assert row.delivered_at is not None
    returned = request_movement(MovementIn(operation_id=uuid4(), professor_id=prof.id, product_id=product.id, quantity=2, kind="RETURN"), db, actor)
    confirm(returned["id"], ConfirmIn(quantity=2), db, admin)
    assert stock.real_quantity == 7
    assert held_quantity(db, prof.id, product.id) == 2
    assert product.stock_global_quantity == 9
    assert dashboard(week, db, actor)["needs"] == []


def test_no_stock_and_partial_pickup(scenario):
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    with pytest.raises(HTTPException) as error:
        deliver(DeliveryIn(assignment_id=row.id, professor_id=prof.id, product_id=product.id), db, actor)
    assert error.value.status_code == 409
    db.refresh(row)
    assert row.delivered_at is None
    result = request_movement(MovementIn(operation_id=uuid4(), professor_id=prof.id, product_id=product.id, quantity=12, kind="PICKUP"), db, actor)
    with pytest.raises(HTTPException):
        confirm(result["id"], ConfirmIn(quantity=12), db, admin)
    confirm(result["id"], ConfirmIn(quantity=3), db, admin)
    assert held_quantity(db, prof.id, product.id) == 3
    assert stock.real_quantity == 7


def test_weekly_dedup_excludes_waitlist_and_follows_reassignment(scenario):
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    duplicate = StudentSheetMusic(student_id=student.id, product_id=product.id, title_snapshot=product.title, status="TO_DELIVER")
    second = CourseSession(course_type_id=session.course_type_id, location_id=session.location_id, professor_id=prof.id,
        snapshot_seller_legal_entity_id=session.snapshot_seller_legal_entity_id, snapshot_payor_legal_entity_id=session.snapshot_payor_legal_entity_id,
        title="Deuxième cours", start_at_utc=session.start_at_utc+timedelta(days=1), end_at_utc=session.end_at_utc+timedelta(days=1),
        capacity_max=6, auto_cancel_deadline_utc=session.start_at_utc, timezone="Europe/Paris")
    db.add_all([duplicate, second]); db.flush()
    db.add(Booking(session_id=second.id, user_id=student.id, status=BookingStatus.BOOKED)); db.flush()
    data = dashboard(week, db, actor)
    assert len(data["needs"]) == 1
    assert data["totals"][0]["needed"] == 1
    other = Professor(email=f"other-{uuid4()}@test.invalid", first_name="Autre", last_name="Prof")
    db.add(other); db.flush()
    session.professor_id = other.id
    db.flush()
    assert dashboard(week, db, actor)["needs"] == []
    assert dashboard(week, db, admin)["needs"][0]["professor_id"] == str(other.id)


def test_professor_cannot_withdraw_for_someone_else(scenario):
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    with pytest.raises(HTTPException) as error:
        request_movement(MovementIn(operation_id=uuid4(), professor_id=uuid4(), product_id=product.id, quantity=1, kind="PICKUP"), db, actor)
    assert error.value.status_code == 403


def test_cancelled_request_never_changes_stock(scenario):
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    result = request_movement(MovementIn(operation_id=uuid4(), professor_id=prof.id, product_id=product.id, quantity=3, kind="PICKUP"), db, actor)
    cancel(result["id"], db, actor)
    with pytest.raises(HTTPException):
        confirm(result["id"], ConfirmIn(quantity=3), db, admin)
    assert stock.real_quantity == 10
    assert held_quantity(db, prof.id, product.id) == 0


def test_change_to_ado_debits_ado_and_keeps_old_book(scenario):
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    pickup(db, admin, actor, prof, product, 1)
    ado = CatalogProduct(title=f"Partition Ado {uuid4()}", active=True, is_virtual=False)
    db.add(ado); db.flush()
    db.add(ProductLocationStock(product_id=ado.id, location_id=stock.location_id, real_quantity=5, estimated_quantity=5)); db.flush()
    pickup(db, admin, actor, prof, ado, 1)
    deliver(DeliveryIn(assignment_id=row.id, professor_id=prof.id, product_id=ado.id), db, actor)
    assert row.product_id == ado.id
    assert row.title_snapshot == ado.title
    assert held_quantity(db, prof.id, product.id) == 1
    assert held_quantity(db, prof.id, ado.id) == 0


def test_waitlisted_students_are_not_pickup_needs(scenario):
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    booking = db.scalar(select(Booking).where(Booking.user_id == student.id))
    booking.status = BookingStatus.WAITLISTED
    db.flush()
    assert dashboard(week, db, actor)["needs"] == []


def test_second_assignment_does_not_cause_second_physical_delivery(scenario):
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    pickup(db, admin, actor, prof, product, 2)
    deliver(DeliveryIn(assignment_id=row.id, professor_id=prof.id, product_id=product.id), db, actor)
    other = StudentSheetMusic(student_id=student.id, product_id=product.id, title_snapshot=product.title, status="TO_DELIVER")
    db.add(other); db.flush()
    with pytest.raises(HTTPException):
        deliver(DeliveryIn(assignment_id=other.id, professor_id=prof.id, product_id=product.id), db, actor)
    assert held_quantity(db, prof.id, product.id) == 1


def test_legacy_delivery_cannot_debit_new_handover_twice(scenario):
    from app.models.product_catalog import ProductRequest, ProductRequestStatus
    from app.services.product_catalog import mark_request_delivered
    db, admin, actor, prof, student, product, stock, row, session, week = scenario
    pickup(db, admin, actor, prof, product, 1)
    deliver(DeliveryIn(assignment_id=row.id, professor_id=prof.id, product_id=product.id), db, actor)
    request = ProductRequest(product_id=product.id, student_user_id=student.id,
        location_id=stock.location_id, quantity=1, status=ProductRequestStatus.TO_DELIVER)
    with pytest.raises(HTTPException) as error:
        mark_request_delivered(db, request_row=request, marker_user_id=admin.id,
            delivered_by_user_id=actor.id, note=None)
    assert error.value.status_code == 409
    assert stock.real_quantity == 9
    assert held_quantity(db, prof.id, product.id) == 0
