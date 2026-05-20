from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.bookings import _forfait_second_course_weekly_applies, _resolve_activity_base_hourly_ttc
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, Location
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, PaymentReceipt
from app.models.plan import ClientForfaitActivityPricing, ClientPlanSubscription
from app.models.quote import Quote, QuoteAcceptanceFollowup
from app.models.user import User
from app.services.payment_receipts import build_booking_receipt_snapshot, get_or_create_pending_booking_payment_receipt

SCRIPT_PREFIX = "PROD_BREETHANY_SECOND_COURSE_FIX"
QUOTE_NUMBER = "DV-20260516050146-F72C"


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


def _split_ttc(total_ttc: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    if vat_rate <= Decimal("0.00"):
        return total_ttc, Decimal("0.00")
    amount_ht = _q2(total_ttc / (Decimal("1.00") + vat_rate / Decimal("100.00")))
    return amount_ht, _q2(total_ttc - amount_ht)


def _is_second_course_transaction(row: ClientManualTransaction) -> bool:
    label = (row.label or "").casefold()
    reference = str(row.reference or "")
    return (
        (row.transaction_type or "").strip().upper() == "DISCOUNT"
        and "2e cours" in label
        and reference.startswith(f"QUOTE:")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Apply {QUOTE_NUMBER} 2nd-course discount on bookings.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, dry-run only.")
    parser.add_argument(
        "--extra-discount-per-hour",
        default="2.00",
        help="TTC discount to add on each second-course booking hour.",
    )
    args = parser.parse_args()
    try:
        configured_extra_discount_per_hour = _q2(Decimal(str(args.extra_discount_per_hour).replace(",", ".")))
    except Exception as exc:
        raise SystemExit(f"[{SCRIPT_PREFIX}] invalid_extra_discount_per_hour={args.extra_discount_per_hour}") from exc
    if configured_extra_discount_per_hour <= Decimal("0.00"):
        raise SystemExit(f"[{SCRIPT_PREFIX}] invalid_extra_discount_per_hour={configured_extra_discount_per_hour}")

    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).limit(1))
        if quote is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] quote_not_found={QUOTE_NUMBER}")

        followup = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == quote.id).limit(1))
        if followup is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] followup_not_found quote_id={quote.id}")

        payload = _json_object(followup.payload)
        execution = _json_object(payload.get("quote_to_enrollment_execution"))
        if str(execution.get("status") or "").strip().lower() != "executed":
            raise SystemExit(f"[{SCRIPT_PREFIX}] transformation_not_executed quote_id={quote.id}")

        booking_ids = _uuid_values(execution.get("created_booking_ids"))
        transaction_ids = _uuid_values(execution.get("created_transaction_ids"))
        subscription_id_raw = str(execution.get("subscription_id") or "").strip()
        subscription_id = UUID(subscription_id_raw) if subscription_id_raw else None
        if not booking_ids or subscription_id is None:
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] missing_execution_ids bookings={len(booking_ids)} transactions={len(transaction_ids)} subscription={subscription_id_raw or '-'}"
            )

        subscription = db.scalar(select(ClientPlanSubscription).where(ClientPlanSubscription.id == subscription_id).with_for_update())
        if subscription is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] subscription_not_found={subscription_id}")

        discount_transactions = [
            row
            for row in db.scalars(
                select(ClientManualTransaction)
                .where(ClientManualTransaction.id.in_(transaction_ids))
                .with_for_update()
            ).all()
            if _is_second_course_transaction(row)
        ]
        if len(discount_transactions) > 1:
            raise SystemExit(f"[{SCRIPT_PREFIX}] ambiguous_second_course_discount_transactions count={len(discount_transactions)}")
        discount_transaction = discount_transactions[0] if discount_transactions else None

        if discount_transaction is not None:
            invoice_line = db.scalar(
                select(ClientInvoiceLine.id)
                .where(
                    ClientInvoiceLine.source == "MANUAL",
                    ClientInvoiceLine.source_payment_id == discount_transaction.id,
                )
                .limit(1)
            )
            if invoice_line is not None:
                raise SystemExit(f"[{SCRIPT_PREFIX}] abort_discount_transaction_locked_by_invoice_line={discount_transaction.id}")

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

        second_rows = [
            (booking, session_obj, course_type, location, student)
            for booking, session_obj, course_type, location, student in booking_rows
            if _forfait_second_course_weekly_applies(
                db,
                subscription=subscription,
                course_type_id=session_obj.course_type_id,
                session_start_at=session_obj.start_at_utc,
                session_timezone=session_obj.timezone,
                booking_id=booking.id,
            )
        ]
        total_second_hours = Decimal("0.00")
        for _, session_obj, course_type, _, _ in second_rows:
            seconds = int(max((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds(), 0))
            if seconds <= 0:
                seconds = int(course_type.duration_minutes or 0) * 60
            total_second_hours += Decimal(seconds) / Decimal("3600")
        if total_second_hours <= Decimal("0.00"):
            raise SystemExit(f"[{SCRIPT_PREFIX}] no_second_course_booking_hours")

        extra_second_discount_per_hour = configured_extra_discount_per_hour

        pricing_rows: dict[UUID, ClientForfaitActivityPricing] = {}
        for _, session_obj, course_type, _, _ in booking_rows:
            pricing = pricing_rows.get(session_obj.course_type_id)
            if pricing is not None:
                continue
            pricing = db.scalar(
                select(ClientForfaitActivityPricing)
                .where(
                    ClientForfaitActivityPricing.subscription_id == subscription.id,
                    ClientForfaitActivityPricing.course_type_id == session_obj.course_type_id,
                )
                .with_for_update()
                .limit(1)
            )
            if pricing is None:
                pricing = ClientForfaitActivityPricing(
                    subscription_id=subscription.id,
                    course_type_id=session_obj.course_type_id,
                    loyalty_discount_per_hour_ttc=Decimal("0.00"),
                    family_discount_per_hour_ttc=Decimal("0.00"),
                    short_commitment_supplement_per_hour_ttc=Decimal("0.00"),
                    second_course_weekly_discount_per_hour_ttc=Decimal("0.00"),
                )
            pricing_rows[session_obj.course_type_id] = pricing

        changed_bookings = 0
        changed_receipts = 0
        changed_pricing = 0
        samples: list[str] = []
        second_booking_ids = {booking.id for booking, *_ in second_rows}

        for course_type_id, pricing in pricing_rows.items():
            loyalty = _q2(Decimal(pricing.loyalty_discount_per_hour_ttc or 0))
            target_second = _q2(loyalty + extra_second_discount_per_hour)
            current_second = _q2(Decimal(pricing.second_course_weekly_discount_per_hour_ttc or 0))
            if current_second != target_second:
                changed_pricing += 1
                if args.apply:
                    pricing.second_course_weekly_discount_per_hour_ttc = target_second
                    db.add(pricing)

        for booking, session_obj, course_type, location, student in booking_rows:
            pricing = pricing_rows[session_obj.course_type_id]
            base_hourly = _q2(_resolve_activity_base_hourly_ttc(course_type))
            loyalty = _q2(Decimal(pricing.loyalty_discount_per_hour_ttc or 0))
            family = _q2(Decimal(pricing.family_discount_per_hour_ttc or 0))
            supplement = _q2(Decimal(pricing.short_commitment_supplement_per_hour_ttc or 0))
            second_discount = _q2(loyalty + extra_second_discount_per_hour) if booking.id in second_booking_ids else loyalty
            effective_primary_discount = second_discount if second_discount > loyalty else loyalty
            seconds = int(max((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds(), 0))
            if seconds <= 0:
                seconds = int(course_type.duration_minutes or 0) * 60
            hours = Decimal(seconds) / Decimal("3600")
            hourly_ttc = _q2(base_hourly - effective_primary_discount - family + supplement)
            if hourly_ttc < Decimal("0.00"):
                hourly_ttc = Decimal("0.00")
            expected_total = _q2(hourly_ttc * hours)
            vat_rate = _q3(Decimal(booking.vat_rate_snapshot or quote.vat_rate or 0))
            amount_ht, vat_amount = _split_ttc(expected_total, vat_rate)
            current_total = _q2(Decimal(booking.total_incl_vat_snapshot or 0))
            if booking.id in second_booking_ids or current_total != expected_total:
                samples.append(
                    f"booking={booking.id}|date={session_obj.start_at_utc.isoformat()}|second={booking.id in second_booking_ids}|current={current_total}|expected={expected_total}|activity={course_type.name}|location={location.name}"
                )
            if current_total == expected_total:
                continue
            changed_bookings += 1
            if not args.apply:
                continue
            booking.vat_rate_snapshot = vat_rate
            booking.price_excl_vat_snapshot = amount_ht
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

        removed_transaction = False
        if args.apply and discount_transaction is not None:
            db.delete(discount_transaction)
            removed_transaction = True
            execution["created_transaction_ids"] = [
                str(value)
                for value in _uuid_values(execution.get("created_transaction_ids"))
                if value != discount_transaction.id
            ]
            payload["quote_to_enrollment_execution"] = execution
            followup.payload = payload
            db.add(followup)
        if args.apply:
            db.commit()
        else:
            db.rollback()

    mode = "apply" if args.apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    print(f"[{SCRIPT_PREFIX}] quote={QUOTE_NUMBER}")
    print(f"[{SCRIPT_PREFIX}] second_course_bookings={len(second_rows)}")
    print(f"[{SCRIPT_PREFIX}] second_course_hours={total_second_hours}")
    print(f"[{SCRIPT_PREFIX}] extra_second_discount_per_hour={extra_second_discount_per_hour}")
    print(f"[{SCRIPT_PREFIX}] changed_pricing_rows={changed_pricing}")
    print(f"[{SCRIPT_PREFIX}] changed_bookings={changed_bookings}")
    print(f"[{SCRIPT_PREFIX}] changed_pending_receipts={changed_receipts}")
    print(f"[{SCRIPT_PREFIX}] removed_global_discount_transaction={removed_transaction}")
    print(f"[{SCRIPT_PREFIX}] global_discount_transaction={discount_transaction.id if discount_transaction is not None else '-'}")
    for sample in samples[:40]:
        print(f"[{SCRIPT_PREFIX}] sample={sample}")


if __name__ == "__main__":
    main()
