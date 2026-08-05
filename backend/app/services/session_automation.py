from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, SessionStatus
from app.models.client_record import ClientManualCreditBalance, PaymentReceipt
from app.models.plan import ClientPlanSubscription, Plan, PlanKind
from app.services.notifications.application.orchestrator import (
    OrchestratedNotification,
    schedule_auto_low_attendance_cancellation_notifications,
)
from app.services.reminders import skip_pending_reminders_for_booking


@dataclass(frozen=True)
class AutoCancelResult:
    checked: int
    cancelled_sessions: int
    cancelled_bookings: int
    notifications: tuple[OrchestratedNotification, ...] = ()


@dataclass(frozen=True)
class PaymentHoldExpirationResult:
    checked: int
    expired_bookings: int
    expired_receipts: int


PAYMENT_TIMEOUT_CANCELLATION_REASON = "PAYMENT_TIMEOUT"


def _restore_cancelled_booking_credit(db: Session, *, booking: Booking) -> None:
    if booking.client_plan_subscription_id is not None:
        row = db.execute(
            select(ClientPlanSubscription, Plan)
            .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
            .where(ClientPlanSubscription.id == booking.client_plan_subscription_id)
            .with_for_update()
        ).first()
        if row is not None:
            subscription, plan = row
            if subscription.user_id == booking.user_id and plan.kind == PlanKind.PACK:
                current = int(subscription.credits_remaining or 0)
                cap = int(subscription.credits_initial) if subscription.credits_initial is not None else current + 1
                subscription.credits_remaining = min(current + 1, cap)
    if booking.manual_credit_type_id is not None:
        balance = db.scalar(
            select(ClientManualCreditBalance)
            .where(
                ClientManualCreditBalance.user_id == booking.user_id,
                ClientManualCreditBalance.credit_type_id == booking.manual_credit_type_id,
            )
            .with_for_update()
        )
        if balance is not None:
            balance.credits_count = int(balance.credits_count or 0) + 1


def _effective_auto_cancel_threshold(db: Session, *, session_obj: CourseSession) -> int | None:
    if session_obj.auto_cancel_rule_enabled_override is False:
        return None
    if session_obj.auto_cancel_rule_enabled_override is True:
        threshold = session_obj.auto_cancel_if_booked_less_than_override
        return int(threshold) if threshold is not None and int(threshold) >= 1 else None
    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    if course_type is None or not bool(course_type.auto_cancel_rule_enabled):
        return None
    threshold = course_type.auto_cancel_if_booked_less_than_override
    return int(threshold) if threshold is not None and int(threshold) >= 1 else None


def run_auto_cancel_empty_sessions_job(db: Session, *, now: datetime, limit: int = 200) -> AutoCancelResult:
    sessions = db.scalars(
        select(CourseSession)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .where(
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.auto_cancel_deadline_utc <= now,
            CourseSession.auto_cancel_checked_at.is_(None),
            CourseSession.start_at_utc > now,
            (
                (CourseSession.auto_cancel_rule_enabled_override.is_(True))
                | (
                    CourseSession.auto_cancel_rule_enabled_override.is_(None)
                    & CourseType.auto_cancel_rule_enabled.is_(True)
                )
            ),
        )
        .order_by(CourseSession.auto_cancel_deadline_utc.asc())
        .limit(limit)
        .with_for_update(of=CourseSession, skip_locked=True)
    ).all()

    cancelled_sessions = 0
    cancelled_bookings = 0
    notifications: list[OrchestratedNotification] = []

    for session_obj in sessions:
        threshold = _effective_auto_cancel_threshold(db, session_obj=session_obj)
        if threshold is None:
            continue
        session_obj.auto_cancel_checked_at = now
        booked_count = int(
            db.scalar(
                select(func.count(Booking.id))
                .where(
                    Booking.session_id == session_obj.id,
                    Booking.status == BookingStatus.BOOKED,
                )
            )
            or 0
        )
        if booked_count >= threshold:
            continue

        bookings = db.scalars(
            select(Booking)
            .where(
                Booking.session_id == session_obj.id,
                Booking.status.in_([BookingStatus.BOOKED, BookingStatus.WAITLISTED]),
            )
            .with_for_update()
        ).all()

        participant_bookings = [booking for booking in bookings if booking.status == BookingStatus.BOOKED]
        notifications.extend(
            schedule_auto_low_attendance_cancellation_notifications(
                db,
                slot=session_obj,
                bookings=participant_bookings,
                booked_count=booked_count,
                minimum_attendees=threshold,
                occurred_at=now,
            )
        )
        session_obj.status = SessionStatus.CANCELLED
        session_obj.cancel_reason = "AUTO_LOW_BOOKINGS"
        cancelled_sessions += 1

        for booking in bookings:
            if booking.status == BookingStatus.BOOKED:
                _restore_cancelled_booking_credit(db, booking=booking)
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = now
            booking.cancellation_reason = "AUTO_SESSION_CANCELLED"
            cancelled_bookings += 1
            skip_pending_reminders_for_booking(
                db,
                booking_id=str(booking.id),
                reason="Session auto-cancelled",
                now=now,
            )

    return AutoCancelResult(
        checked=len(sessions),
        cancelled_sessions=cancelled_sessions,
        cancelled_bookings=cancelled_bookings,
        notifications=tuple(notifications),
    )


def run_expire_pending_payment_bookings_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 200,
) -> PaymentHoldExpirationResult:
    bookings = db.scalars(
        select(Booking)
        .where(
            Booking.status == BookingStatus.PENDING_PAYMENT,
            Booking.payment_hold_expires_at.is_not(None),
            Booking.payment_hold_expires_at <= now,
        )
        .order_by(Booking.payment_hold_expires_at.asc(), Booking.booked_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    expired_receipts = 0
    for booking in bookings:
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.cancellation_reason = PAYMENT_TIMEOUT_CANCELLATION_REASON
        booking.payment_hold_expires_at = None
        skip_pending_reminders_for_booking(
            db,
            booking_id=str(booking.id),
            reason="Pending payment expired",
            now=now,
        )
        receipts = db.scalars(
            select(PaymentReceipt)
            .where(
                PaymentReceipt.booking_id == booking.id,
                PaymentReceipt.status == "PENDING",
                PaymentReceipt.final_invoice_note_id.is_(None),
            )
            .with_for_update()
        ).all()
        for receipt in receipts:
            metadata = dict(receipt.receipt_metadata or {})
            metadata["booking_hold_expired_at"] = now.isoformat()
            receipt.status = "EXPIRED"
            receipt.receipt_metadata = metadata
            receipt.updated_at = now
            db.add(receipt)
            expired_receipts += 1

    return PaymentHoldExpirationResult(
        checked=len(bookings),
        expired_bookings=len(bookings),
        expired_receipts=expired_receipts,
    )
