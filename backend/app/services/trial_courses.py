from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession
from app.models.plan import ClientPlanSubscription, Plan, SubscriptionStatus
from app.services.plan_entitlements import effective_entitlements_by_plan


TRIAL_USAGE_STATUSES: tuple[BookingStatus, ...] = (
    BookingStatus.BOOKED,
    BookingStatus.PENDING_PAYMENT,
    BookingStatus.WAITLISTED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)

TRIAL_CREDIT_STATUSES: tuple[SubscriptionStatus, ...] = (
    SubscriptionStatus.PENDING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAYMENT_ALERT,
    SubscriptionStatus.PAUSED,
)


def trial_plan_course_type_ids(db: Session, *, plan_id: UUID) -> set[UUID]:
    ids_by_plan, _ = effective_entitlements_by_plan(db, plan_ids=[plan_id])
    return set(ids_by_plan.get(plan_id, []))


def plan_supports_trial_course_type(db: Session, *, plan_id: UUID, course_type_id: UUID) -> bool:
    return course_type_id in trial_plan_course_type_ids(db, plan_id=plan_id)


def has_trial_booking_for_course_type(
    db: Session,
    *,
    user_id: UUID,
    course_type_id: UUID,
    exclude_booking_id: UUID | None = None,
) -> bool:
    stmt = (
        select(Booking.id)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .where(
            Booking.user_id == user_id,
            Booking.is_trial_course.is_(True),
            Booking.status.in_(TRIAL_USAGE_STATUSES),
            CourseSession.course_type_id == course_type_id,
        )
        .limit(1)
    )
    if exclude_booking_id is not None:
        stmt = stmt.where(Booking.id != exclude_booking_id)
    return db.scalar(stmt) is not None


def has_prior_course_attendance_for_course_type(
    db: Session,
    *,
    user_id: UUID,
    course_type_id: UUID,
    reference_at: datetime,
) -> bool:
    """Return whether the participant has already followed this course type.

    ATTENDED is authoritative. A past BOOKED session is also counted because
    attendance may not have been closed yet; cancellations, no-shows and
    excused absences are not treated as a course followed.
    """

    return (
        db.scalar(
            select(Booking.id)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == user_id,
                CourseSession.course_type_id == course_type_id,
                or_(
                    Booking.status == BookingStatus.ATTENDED,
                    and_(
                        Booking.status == BookingStatus.BOOKED,
                        CourseSession.end_at_utc <= reference_at,
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


def has_available_trial_credit(
    db: Session,
    *,
    user_id: UUID,
    plan_id: UUID,
) -> bool:
    return (
        db.scalar(
            select(ClientPlanSubscription.id)
            .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
            .where(
                ClientPlanSubscription.user_id == user_id,
                ClientPlanSubscription.plan_id == plan_id,
                ClientPlanSubscription.status.in_(TRIAL_CREDIT_STATUSES),
                ClientPlanSubscription.credits_remaining.is_not(None),
                ClientPlanSubscription.credits_remaining > 0,
                Plan.is_trial_offer.is_(True),
            )
            .limit(1)
        )
        is not None
    )


def has_available_trial_credit_for_course_type(
    db: Session,
    *,
    user_id: UUID,
    course_type_id: UUID,
) -> bool:
    plan_ids = list(
        dict.fromkeys(
            db.scalars(
                select(ClientPlanSubscription.plan_id)
                .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
                .where(
                    ClientPlanSubscription.user_id == user_id,
                    ClientPlanSubscription.status.in_(TRIAL_CREDIT_STATUSES),
                    ClientPlanSubscription.credits_remaining.is_not(None),
                    ClientPlanSubscription.credits_remaining > 0,
                    Plan.is_trial_offer.is_(True),
                )
            ).all()
        )
    )
    if not plan_ids:
        return False
    ids_by_plan, _ = effective_entitlements_by_plan(db, plan_ids=plan_ids)
    return any(course_type_id in ids_by_plan.get(plan_id, []) for plan_id in plan_ids)


__all__ = [
    "TRIAL_USAGE_STATUSES",
    "has_available_trial_credit",
    "has_available_trial_credit_for_course_type",
    "has_prior_course_attendance_for_course_type",
    "has_trial_booking_for_course_type",
    "plan_supports_trial_course_type",
    "trial_plan_course_type_ids",
]
