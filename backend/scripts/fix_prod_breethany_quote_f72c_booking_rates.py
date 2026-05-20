from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, Location
from app.models.client_record import ClientInvoiceLine, PaymentReceipt
from app.models.plan import ClientForfaitActivityPricing, ClientPlanSubscription
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.models.user import User
from app.services.payment_receipts import build_booking_receipt_snapshot, get_or_create_pending_booking_payment_receipt

SCRIPT_PREFIX = "PROD_BREETHANY_F72C_RATE_FIX"
QUOTE_NUMBER = "DV-20260516050146-F72C"
EXPECTED_CURRENT_TOTAL_TTC = Decimal("35.00")


@dataclass(frozen=True)
class ActivityRate:
    course_type_id: UUID
    expected_hourly_ttc: Decimal
    vat_rate: Decimal


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _q3(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"))


def _json_object(value: object | None) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _json_list(value: object | None) -> list[object]:
    return value if isinstance(value, list) else []


def _uuid_values(values: object | None) -> list[UUID]:
    out: list[UUID] = []
    for value in _json_list(values):
        try:
            out.append(UUID(str(value)))
        except ValueError:
            continue
    return out


def _activity_rates_from_quote(db, lines: list[QuoteLine]) -> dict[UUID, ActivityRate]:
    course_type_by_id: dict[UUID, CourseType] = {}
    totals: dict[UUID, dict[str, Decimal]] = defaultdict(lambda: {"amount_ttc": Decimal("0.00"), "hours": Decimal("0.00"), "vat_rate": Decimal("0.00")})
    for line in lines:
        if line.activity_id is None:
            continue
        if (line.line_category or "").strip().lower() != "service":
            continue
        if (line.line_type or "").strip().lower() != "item":
            continue
        quantity = _q2(Decimal(line.quantity or 0))
        course_type = course_type_by_id.get(line.activity_id)
        if course_type is None:
            course_type = db.scalar(select(CourseType).where(CourseType.id == line.activity_id))
            if course_type is not None:
                course_type_by_id[line.activity_id] = course_type
        duration_minutes = int(line.duration_minutes or (course_type.duration_minutes if course_type is not None else 0) or 0)
        if quantity <= Decimal("0.00") or duration_minutes <= 0:
            continue
        hours = (quantity * Decimal(duration_minutes)) / Decimal("60")
        if hours <= Decimal("0.00"):
            continue
        bucket = totals[line.activity_id]
        bucket["amount_ttc"] += _q2(Decimal(line.amount_ttc or 0))
        bucket["hours"] += hours
        bucket["vat_rate"] = _q3(Decimal(line.vat_rate or 0))

    rates: dict[UUID, ActivityRate] = {}
    for course_type_id, values in totals.items():
        if values["hours"] <= Decimal("0.00"):
            continue
        rates[course_type_id] = ActivityRate(
            course_type_id=course_type_id,
            expected_hourly_ttc=_q2(values["amount_ttc"] / values["hours"]),
            vat_rate=_q3(values["vat_rate"]),
        )
    return rates


def _base_hourly_ttc(course_type: CourseType) -> Decimal | None:
    if course_type.default_course_rate_ttc is not None:
        reference_minutes = int(course_type.duration_minutes or 0)
        if reference_minutes <= 0:
            return None
        return _q2(Decimal(course_type.default_course_rate_ttc) / (Decimal(reference_minutes) / Decimal("60")))
    if course_type.default_hourly_rate is not None:
        return _q2(Decimal(course_type.default_hourly_rate))
    return None


def _split_ttc(total_ttc: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    if vat_rate <= Decimal("0.00"):
        return total_ttc, Decimal("0.00")
    divisor = Decimal("1.00") + (vat_rate / Decimal("100.00"))
    amount_ht = _q2(total_ttc / divisor)
    return amount_ht, _q2(total_ttc - amount_ht)


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Fix transformed booking rates for {QUOTE_NUMBER}.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, dry-run only.")
    args = parser.parse_args()

    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).limit(1))
        if quote is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] quote_not_found={QUOTE_NUMBER}")

        followup = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == quote.id).limit(1))
        if followup is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] followup_not_found quote_id={quote.id}")

        execution = _json_object(_json_object(followup.payload).get("quote_to_enrollment_execution"))
        if str(execution.get("status") or "").strip().lower() != "executed":
            raise SystemExit(f"[{SCRIPT_PREFIX}] transformation_not_executed quote_id={quote.id}")

        booking_ids = _uuid_values(execution.get("created_booking_ids"))
        subscription_id_raw = str(execution.get("subscription_id") or "").strip()
        subscription_id = UUID(subscription_id_raw) if subscription_id_raw else None
        if not booking_ids or subscription_id is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] missing_booking_or_subscription_ids booking_count={len(booking_ids)} subscription_id={subscription_id_raw or '-'}")

        subscription = db.scalar(select(ClientPlanSubscription).where(ClientPlanSubscription.id == subscription_id).with_for_update())
        if subscription is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] subscription_not_found={subscription_id}")

        quote_lines = db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id)).all()
        rates = _activity_rates_from_quote(db, quote_lines)
        if not rates:
            raise SystemExit(f"[{SCRIPT_PREFIX}] no_service_rates_from_quote quote_id={quote.id}")

        booking_rows = db.execute(
            select(Booking, CourseSession, CourseType, Location, User)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .join(User, User.id == Booking.user_id)
            .where(Booking.id.in_(booking_ids))
            .with_for_update()
            .order_by(CourseSession.start_at_utc.asc(), Booking.id.asc())
        ).all()
        if len(booking_rows) != len(booking_ids):
            raise SystemExit(f"[{SCRIPT_PREFIX}] booking_count_mismatch expected={len(booking_ids)} found={len(booking_rows)}")

        invoice_line_count = db.scalar(
            select(ClientInvoiceLine.id)
            .where(
                ClientInvoiceLine.source == "BOOKING",
                ClientInvoiceLine.source_payment_id.in_(booking_ids),
            )
            .limit(1)
        )
        if invoice_line_count is not None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] abort_booking_invoice_line_exists")

        changed_bookings = 0
        changed_receipts = 0
        changed_pricing_rows = 0
        samples: list[str] = []

        for course_type_id, rate in rates.items():
            course_type = db.scalar(select(CourseType).where(CourseType.id == course_type_id))
            if course_type is None:
                continue
            base = _base_hourly_ttc(course_type)
            if base is None:
                continue
            delta = _q2(base - rate.expected_hourly_ttc)
            loyalty = delta if delta > Decimal("0.00") else Decimal("0.00")
            supplement = abs(delta) if delta < Decimal("0.00") else Decimal("0.00")
            pricing = db.scalar(
                select(ClientForfaitActivityPricing)
                .where(
                    ClientForfaitActivityPricing.subscription_id == subscription.id,
                    ClientForfaitActivityPricing.course_type_id == course_type_id,
                )
                .with_for_update()
                .limit(1)
            )
            if pricing is None:
                pricing = ClientForfaitActivityPricing(
                    subscription_id=subscription.id,
                    course_type_id=course_type_id,
                    loyalty_discount_per_hour_ttc=loyalty,
                    family_discount_per_hour_ttc=Decimal("0.00"),
                    short_commitment_supplement_per_hour_ttc=supplement,
                    second_course_weekly_discount_per_hour_ttc=Decimal("0.00"),
                )
                changed_pricing_rows += 1
            elif (
                _q2(Decimal(pricing.loyalty_discount_per_hour_ttc or 0)) != loyalty
                or _q2(Decimal(pricing.family_discount_per_hour_ttc or 0)) != Decimal("0.00")
                or _q2(Decimal(pricing.short_commitment_supplement_per_hour_ttc or 0)) != supplement
            ):
                pricing.loyalty_discount_per_hour_ttc = loyalty
                pricing.family_discount_per_hour_ttc = Decimal("0.00")
                pricing.short_commitment_supplement_per_hour_ttc = supplement
                changed_pricing_rows += 1
            if args.apply:
                db.add(pricing)

        if (
            _q2(Decimal(subscription.forfait_loyalty_discount_per_hour_ttc or 0)) != Decimal("0.00")
            or _q2(Decimal(subscription.forfait_family_discount_per_hour_ttc or 0)) != Decimal("0.00")
        ):
            subscription.forfait_loyalty_discount_per_hour_ttc = Decimal("0.00")
            subscription.forfait_family_discount_per_hour_ttc = Decimal("0.00")
            if args.apply:
                db.add(subscription)

        for booking, session_obj, course_type, location, student in booking_rows:
            rate = rates.get(session_obj.course_type_id)
            if rate is None:
                raise SystemExit(f"[{SCRIPT_PREFIX}] booking_activity_not_in_quote booking={booking.id} course_type={session_obj.course_type_id}")
            duration_hours = Decimal(max(int((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds()), 0)) / Decimal("3600")
            if duration_hours <= Decimal("0.00"):
                duration_hours = Decimal(int(course_type.duration_minutes or 0)) / Decimal("60")
            expected_total = _q2(rate.expected_hourly_ttc * duration_hours)
            amount_ht, vat_amount = _split_ttc(expected_total, rate.vat_rate)
            current_total = _q2(Decimal(booking.total_incl_vat_snapshot or 0))
            samples.append(
                f"booking={booking.id}|date={session_obj.start_at_utc.isoformat()}|activity={course_type.name}|location={location.name}|current={current_total}|expected={expected_total}"
            )
            if current_total == expected_total:
                continue
            if current_total != EXPECTED_CURRENT_TOTAL_TTC:
                raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected_current_total booking={booking.id} current={current_total} expected_old={EXPECTED_CURRENT_TOTAL_TTC}")
            changed_bookings += 1
            if not args.apply:
                continue
            booking.price_excl_vat_snapshot = amount_ht
            booking.vat_rate_snapshot = rate.vat_rate
            booking.vat_amount_snapshot = vat_amount
            booking.total_incl_vat_snapshot = expected_total
            booking.currency_snapshot = (quote.currency or "EUR").upper()
            db.add(booking)

            snapshot = build_booking_receipt_snapshot(
                db,
                booking=booking,
                session_obj=session_obj,
                course_type=course_type,
                location=location,
                owner=student,
            )
            before_receipt = db.scalar(
                select(PaymentReceipt.id)
                .where(
                    PaymentReceipt.booking_id == booking.id,
                    PaymentReceipt.status == "PENDING",
                    PaymentReceipt.final_invoice_note_id.is_(None),
                )
                .limit(1)
            )
            get_or_create_pending_booking_payment_receipt(db, booking=booking, snapshot=snapshot)
            after_receipt = db.scalar(
                select(PaymentReceipt.id)
                .where(
                    PaymentReceipt.booking_id == booking.id,
                    PaymentReceipt.status == "PENDING",
                    PaymentReceipt.final_invoice_note_id.is_(None),
                )
                .limit(1)
            )
            if before_receipt is not None or after_receipt is not None:
                changed_receipts += 1

        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode = "apply" if args.apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    print(f"[{SCRIPT_PREFIX}] quote={QUOTE_NUMBER}")
    print(f"[{SCRIPT_PREFIX}] subscription_id={subscription_id}")
    print(f"[{SCRIPT_PREFIX}] booking_count={len(booking_rows)}")
    print(f"[{SCRIPT_PREFIX}] changed_bookings={changed_bookings}")
    print(f"[{SCRIPT_PREFIX}] changed_pending_receipts={changed_receipts}")
    print(f"[{SCRIPT_PREFIX}] changed_pricing_rows={changed_pricing_rows}")
    for sample in samples[:20]:
        print(f"[{SCRIPT_PREFIX}] sample={sample}")


if __name__ == "__main__":
    main()
