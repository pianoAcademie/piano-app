from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.models.catalog import (
    Booking,
    CourseSession,
    CourseType,
    DeliveryMode,
    LessonFormat,
    Location,
    PlanningCourseType,
    SessionStatus,
)
from app.models.payout import ProfessorPayGridBracket, ProfessorPayGridPeriod, ProfessorPayGridRule
from app.models.plan import Plan, PlanCreditGrant, PlanEntitlement
from app.models.quote import PricingActivityPrice, PricingCatalog


SCRIPT_PREFIX = "child-group-trial-20260902"
SOURCE_ACTIVITY_CODE = "PIANO_GROUP_ONSITE_1H"
TARGET_ACTIVITY_CODE = "ACT_COURS_D_ESSAI_COLLECTIF_2DE0E7"
TARGET_ACTIVITY_NAME = "Cours d'essai collectif enfants"
TARGET_LOCATION_CODES = {"ASSAS", "RICHELIEU", "POMPE", "DULONG", "SCHEFFER"}
TRIAL_PRICE = Decimal("20.00")
TARGET_DURATION_MINUTES = 30
TARGET_CAPACITY = 6


def _trial_plan_for_activity(db, *, activity_id):
    return db.scalar(
        select(Plan)
        .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id)
        .where(
            PlanEntitlement.course_type_id == activity_id,
            Plan.is_trial_offer.is_(True),
            Plan.active.is_(True),
            Plan.is_private.is_(False),
        )
        .order_by(Plan.created_at.asc())
        .limit(1)
    )


def run(*, apply: bool) -> None:
    with SessionLocal() as db:
        source = db.scalar(select(CourseType).where(CourseType.code == SOURCE_ACTIVITY_CODE))
        target = db.scalar(select(CourseType).where(CourseType.code == TARGET_ACTIVITY_CODE))
        if source is None:
            raise RuntimeError(f"Source activity {SOURCE_ACTIVITY_CODE} not found")
        if target is None:
            raise RuntimeError(f"Target activity {TARGET_ACTIVITY_CODE} not found")

        now = datetime.now(timezone.utc)
        changed_activity = 0
        expected_activity_values = {
            "name": TARGET_ACTIVITY_NAME,
            "description": "Cours d'essai collectif de piano pour enfants, 30 minutes, 6 participants maximum.",
            "service_code": source.service_code,
            "billing_entity_code": source.billing_entity_code,
            "seller_legal_entity_id": source.seller_legal_entity_id,
            "payor_legal_entity_id": source.payor_legal_entity_id,
            "credit_type_id": source.credit_type_id,
            "duration_minutes": TARGET_DURATION_MINUTES,
            "mode": DeliveryMode.ONSITE,
            "lesson_format": LessonFormat.GROUP,
            "requires_professor": True,
            "allows_student_bookings": True,
            "supports_student_time_overrides": False,
            "default_capacity": TARGET_CAPACITY,
            "default_hourly_rate": source.default_hourly_rate,
            "trial_course_enabled": True,
            "trial_course_price_ttc": TRIAL_PRICE,
            "active": True,
        }
        for field, expected in expected_activity_values.items():
            if getattr(target, field) != expected:
                setattr(target, field, expected)
                changed_activity = 1
        if changed_activity:
            target.updated_at = now
            db.add(target)

        locations = db.scalars(select(Location).where(Location.code.in_(TARGET_LOCATION_CODES))).all()
        location_by_code = {location.code: location for location in locations}
        missing_location_codes = TARGET_LOCATION_CODES - set(location_by_code)
        if missing_location_codes:
            raise RuntimeError(f"Missing locations: {sorted(missing_location_codes)}")

        existing_planning_rows = db.scalars(
            select(PlanningCourseType).where(PlanningCourseType.course_type_id == target.id)
        ).all()
        desired_location_ids = {location.id for location in locations}
        removed_planning = 0
        for row in existing_planning_rows:
            if row.location_id not in desired_location_ids:
                db.delete(row)
                removed_planning += 1
        existing_location_ids = {row.location_id for row in existing_planning_rows}
        added_planning = 0
        for location in locations:
            if location.id in existing_location_ids:
                continue
            max_order = db.scalar(
                select(func.max(PlanningCourseType.display_order)).where(
                    PlanningCourseType.location_id == location.id
                )
            )
            db.add(
                PlanningCourseType(
                    location_id=location.id,
                    course_type_id=target.id,
                    display_order=int(max_order or 0) + 1,
                )
            )
            added_planning += 1

        source_trial_plan = _trial_plan_for_activity(db, activity_id=source.id)
        if source_trial_plan is None:
            raise RuntimeError("No active public trial plan is linked to the onsite group activity")
        added_entitlement = 0
        if db.scalar(
            select(PlanEntitlement.id).where(
                PlanEntitlement.plan_id == source_trial_plan.id,
                PlanEntitlement.course_type_id == target.id,
            )
        ) is None:
            db.add(PlanEntitlement(plan_id=source_trial_plan.id, course_type_id=target.id))
            added_entitlement = 1
        added_credit_grant = 0
        if target.credit_type_id is not None and db.scalar(
            select(PlanCreditGrant.id).where(
                PlanCreditGrant.plan_id == source_trial_plan.id,
                PlanCreditGrant.credit_type_id == target.credit_type_id,
            )
        ) is None:
            db.add(
                PlanCreditGrant(
                    plan_id=source_trial_plan.id,
                    credit_type_id=target.credit_type_id,
                    credits_count=1,
                    updated_at=now,
                )
            )
            added_credit_grant = 1

        published_catalog = db.scalar(
            select(PricingCatalog)
            .where(
                PricingCatalog.is_active.is_(True),
                PricingCatalog.lifecycle_status == "PUBLISHED",
                PricingCatalog.published_at.is_not(None),
                PricingCatalog.effective_from <= now,
            )
            .order_by(PricingCatalog.is_default.desc(), PricingCatalog.effective_from.desc())
            .limit(1)
        )
        if published_catalog is None:
            raise RuntimeError("No active published pricing catalog found")
        external_price = db.scalar(
            select(PricingActivityPrice)
            .where(
                PricingActivityPrice.catalog_id == published_catalog.id,
                PricingActivityPrice.activity_id == target.id,
                PricingActivityPrice.location_id.is_(None),
                PricingActivityPrice.student_category.is_(None),
                PricingActivityPrice.pricing_unit == "per_session",
                PricingActivityPrice.price_channel == "EXTERNAL_UNIT",
            )
            .order_by(PricingActivityPrice.updated_at.desc())
            .limit(1)
        )
        added_external_price = 0
        if external_price is None:
            external_price = PricingActivityPrice(
                catalog_id=published_catalog.id,
                activity_id=target.id,
                location_id=None,
                student_category=None,
                pricing_unit="per_session",
                price_channel="EXTERNAL_UNIT",
                unit_price_ttc=TRIAL_PRICE,
                currency="EUR",
                is_active=True,
                updated_at=now,
            )
            db.add(external_price)
            added_external_price = 1
        else:
            external_price.unit_price_ttc = TRIAL_PRICE
            external_price.currency = "EUR"
            external_price.is_active = True
            external_price.updated_at = now
            db.add(external_price)

        copied_pay_rules = 0
        copied_pay_brackets = 0
        periods = db.scalars(
            select(ProfessorPayGridPeriod).where(ProfessorPayGridPeriod.status != "ARCHIVED")
        ).all()
        for period in periods:
            source_rule = db.scalar(
                select(ProfessorPayGridRule).where(
                    ProfessorPayGridRule.period_id == period.id,
                    ProfessorPayGridRule.course_type_id == source.id,
                )
            )
            if source_rule is None:
                continue
            target_rule = db.scalar(
                select(ProfessorPayGridRule).where(
                    ProfessorPayGridRule.period_id == period.id,
                    ProfessorPayGridRule.course_type_id == target.id,
                )
            )
            if target_rule is None:
                target_rule = ProfessorPayGridRule(
                    period_id=period.id,
                    course_type_id=target.id,
                    sort_order=source_rule.sort_order + 1,
                )
                db.add(target_rule)
                db.flush()
            target_rule.mode = source_rule.mode
            target_rule.reference_duration_minutes = TARGET_DURATION_MINUTES
            target_rule.currency_code = source_rule.currency_code
            target_rule.default_hourly_rate = source_rule.default_hourly_rate
            target_rule.updated_at = now
            db.add(target_rule)
            db.execute(delete(ProfessorPayGridBracket).where(ProfessorPayGridBracket.rule_id == target_rule.id))
            source_brackets = db.scalars(
                select(ProfessorPayGridBracket)
                .where(ProfessorPayGridBracket.rule_id == source_rule.id)
                .order_by(ProfessorPayGridBracket.sort_order, ProfessorPayGridBracket.min_students)
            ).all()
            for source_bracket in source_brackets:
                db.add(
                    ProfessorPayGridBracket(
                        rule_id=target_rule.id,
                        min_students=source_bracket.min_students,
                        max_students=source_bracket.max_students,
                        hourly_rate=source_bracket.hourly_rate,
                        sort_order=source_bracket.sort_order,
                        updated_at=now,
                    )
                )
                copied_pay_brackets += 1
            copied_pay_rules += 1

        updated_future_sessions = 0
        skipped_future_sessions_with_bookings = 0
        future_sessions = db.scalars(
            select(CourseSession).where(
                CourseSession.course_type_id == target.id,
                CourseSession.status == SessionStatus.SCHEDULED,
                CourseSession.start_at_utc > now,
            )
        ).all()
        for session in future_sessions:
            bookings_count = db.scalar(
                select(func.count(Booking.id)).where(Booking.session_id == session.id)
            )
            if int(bookings_count or 0) > 0:
                skipped_future_sessions_with_bookings += 1
                continue
            session.end_at_utc = session.start_at_utc + timedelta(minutes=TARGET_DURATION_MINUTES)
            session.capacity_max = TARGET_CAPACITY
            session.child_bookings_enabled = True
            session.adult_bookings_enabled = False
            session.adult_capacity_max = None
            session.child_trial_bookings_enabled = True
            session.adult_trial_bookings_enabled = False
            session.updated_at = now
            db.add(session)
            updated_future_sessions += 1

        print(
            f"[{SCRIPT_PREFIX}] mode={'apply' if apply else 'dry-run'}|activity_id={target.id}|"
            f"changed_activity={changed_activity}|added_planning={added_planning}|"
            f"removed_planning={removed_planning}|added_entitlement={added_entitlement}|"
            f"added_credit_grant={added_credit_grant}|added_external_price={added_external_price}|"
            f"copied_pay_rules={copied_pay_rules}|"
            f"copied_pay_brackets={copied_pay_brackets}|updated_future_sessions={updated_future_sessions}|"
            f"skipped_future_sessions_with_bookings={skipped_future_sessions_with_bookings}"
        )
        if apply:
            db.commit()
            print(f"[{SCRIPT_PREFIX}] committed=true")
        else:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
