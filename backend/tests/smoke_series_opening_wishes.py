"""Exercise production-shaped data inside an outer transaction that is rolled back."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models import Booking, CourseSession, User, UserRole
from app.api.routes import admin
from app.schemas.admin import AdminAnnualSeriesTransferRequestCreate, AdminAnnualSeriesTransferStatusUpdate

base = SessionLocal()
connection = base.get_bind().connect()
outer = connection.begin()
db = Session(bind=connection, join_transaction_mode="create_savepoint")
try:
    actor = db.scalar(select(User).where(User.role == UserRole.ADMIN).limit(1))
    booking = db.scalar(select(Booking).join(CourseSession, CourseSession.id == Booking.session_id).where(Booking.status.in_(admin.BOOKING_STATUSES_ACTIVE), CourseSession.recurrence_group_id.is_not(None), CourseSession.start_at_utc > admin._utcnow()).limit(1))
    before = (booking.status, booking.session_id, booking.total_incl_vat_snapshot)
    created = admin.create_annual_series_transfer(AdminAnnualSeriesTransferRequestCreate(student_user_id=booking.user_id, source_booking_id=booking.id, desired_weekday=6, desired_time="03:17", internal_note="ROLLBACK SMOKE TEST"), db=db, actor=actor)
    assert created.status == "WAITING_OPENING"
    assert created.target_session_id is None
    assert "dimanche 03:17" in created.target_label
    assert not created.place_available
    admin.update_annual_series_transfer_status(created.id, AdminAnnualSeriesTransferStatusUpdate(status="CANCELLED"), db=db, actor=actor)
    db.refresh(booking)
    assert before == (booking.status, booking.session_id, booking.total_incl_vat_snapshot)
    print("PASS: create, list, label, cancel, original booking unchanged; rolling back all test data")
finally:
    db.close()
    outer.rollback()
    connection.close()
    base.close()
