from __future__ import annotations

import argparse
import os
import sys
from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession
from app.models.client_record import ClientInvoiceLine, PaymentReceipt
from app.models.user import User


SCRIPT_PREFIX = "PROD_REPAIR_MELINE_FLOT_JUNE_BOOKINGS"
STUDENT_ID = UUID("4403cdfc-dfcf-434f-9512-d872839d7741")
TARGET_SESSION_IDS = (
    UUID("bd4a31b6-dc42-4f16-9753-365d03b4c2d9"),  # 2027-06-16 15:30 Europe/Paris
    UUID("91f8ec49-12c8-4076-a84b-d544f47478ba"),  # 2027-06-23 15:30 Europe/Paris
)
EXPECTED_TARGET_DATES = {date(2027, 6, 16), date(2027, 6, 23)}
EXPECTED_SOURCE_TOTAL = Decimal("22.00")
EXPECTED_PRE_REPAIR_TOTAL = Decimal("26.00")

PRICING_FIELDS = (
    "price_excl_vat_snapshot",
    "vat_rate_snapshot",
    "vat_amount_snapshot",
    "total_incl_vat_snapshot",
    "currency_snapshot",
    "pricing_snapshot_locked",
    "pricing_channel_snapshot",
    "pricing_source_snapshot",
    "pricing_unit_snapshot",
    "price_book_version_snapshot",
    "pricing_breakdown_snapshot",
    "pricing_calculated_at",
)


def _money(value: object) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Attach Meline Flot's two June 2027 bookings to her annual package and restore the 22 EUR rate."
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes. Without it, dry-run only.")
    args = parser.parse_args()

    with SessionLocal() as db:
        student = db.scalar(select(User).where(User.id == STUDENT_ID).with_for_update())
        if student is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] abort|reason=student_not_found")

        target_rows = db.execute(
            select(Booking, CourseSession)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(Booking.user_id == STUDENT_ID, Booking.session_id.in_(TARGET_SESSION_IDS))
            .order_by(CourseSession.start_at_utc.asc())
            .with_for_update()
        ).all()
        if len(target_rows) != 2:
            raise SystemExit(f"[{SCRIPT_PREFIX}] abort|reason=target_booking_count|actual={len(target_rows)}")

        target_dates = {session.start_at_utc.date() for _, session in target_rows}
        if target_dates != EXPECTED_TARGET_DATES:
            raise SystemExit(f"[{SCRIPT_PREFIX}] abort|reason=target_dates|actual={sorted(target_dates)}")

        source_rows = db.execute(
            select(Booking, CourseSession)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.user_id == STUDENT_ID,
                Booking.status == BookingStatus.BOOKED,
                CourseSession.recurrence_group_id == target_rows[0][1].recurrence_group_id,
                CourseSession.start_at_utc < target_rows[0][1].start_at_utc,
            )
            .order_by(CourseSession.start_at_utc.desc())
            .with_for_update()
        ).all()
        source = next(
            (
                booking
                for booking, _ in source_rows
                if booking.client_plan_subscription_id is not None
                and _money(booking.total_incl_vat_snapshot) == EXPECTED_SOURCE_TOTAL
            ),
            None,
        )
        if source is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] abort|reason=source_booking_not_found")

        target_booking_ids = [booking.id for booking, _ in target_rows]
        receipt_count = int(
            db.scalar(select(func.count(PaymentReceipt.id)).where(PaymentReceipt.booking_id.in_(target_booking_ids))) or 0
        )
        invoice_line_count = int(
            db.scalar(
                select(func.count(ClientInvoiceLine.id)).where(
                    ClientInvoiceLine.source_payment_id.in_(target_booking_ids)
                )
            )
            or 0
        )
        if receipt_count or invoice_line_count:
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] abort|reason=already_financialized|receipts={receipt_count}|invoice_lines={invoice_line_count}"
            )

        changed = 0
        for booking, session in target_rows:
            current_total = _money(booking.total_incl_vat_snapshot)
            already_repaired = (
                booking.client_plan_subscription_id == source.client_plan_subscription_id
                and current_total == EXPECTED_SOURCE_TOTAL
            )
            print(
                f"[{SCRIPT_PREFIX}] target|booking={booking.id}|session={session.id}|date={session.start_at_utc.date()}|"
                f"status={booking.status.value}|subscription={booking.client_plan_subscription_id or '-'}|total={current_total}|"
                f"already_repaired={str(already_repaired).lower()}"
            )
            if already_repaired:
                continue
            if booking.status != BookingStatus.BOOKED:
                raise SystemExit(
                    f"[{SCRIPT_PREFIX}] abort|reason=unexpected_status|booking={booking.id}|status={booking.status.value}"
                )
            if booking.client_plan_subscription_id is not None or current_total != EXPECTED_PRE_REPAIR_TOTAL:
                raise SystemExit(
                    f"[{SCRIPT_PREFIX}] abort|reason=unexpected_target_state|booking={booking.id}|"
                    f"subscription={booking.client_plan_subscription_id or '-'}|total={current_total}"
                )

            booking.client_plan_subscription_id = source.client_plan_subscription_id
            booking.manual_credit_type_id = source.manual_credit_type_id
            for field in PRICING_FIELDS:
                setattr(booking, field, deepcopy(getattr(source, field)))
            db.add(booking)
            changed += 1

        print(
            f"[{SCRIPT_PREFIX}] source|booking={source.id}|subscription={source.client_plan_subscription_id}|"
            f"total={_money(source.total_incl_vat_snapshot)}"
        )
        print(f"[{SCRIPT_PREFIX}] planned_changes={changed}")

        if args.apply:
            db.commit()
        else:
            db.rollback()

    result = "already_repaired" if changed == 0 else ("applied" if args.apply else "planned")
    print(f"[{SCRIPT_PREFIX}] summary|result={result}|mode={'apply' if args.apply else 'dry-run'}|changed={changed}")


if __name__ == "__main__":
    main()
