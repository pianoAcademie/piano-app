from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType
from app.models.client_record import ClientInvoiceLine
from app.models.user import User


SCRIPT_PREFIX = "PROD_REPAIR_LIAM_ANGO_BOOKING_PRICES"
TARGET_USER_ID = UUID("6b30fa9e-f80c-4363-950a-3557fbbadda2")
TARGET_SUBSCRIPTION_ID = UUID("0b081e8e-b597-4349-a654-d880aa4a7980")
TARGET_PRICE = Decimal("22.00")
TARGET_BOOKING_COUNT = 31
TARGET_COURSE_TYPE_NAMES = {
    "Cours collectifs ado/adultes",
    "Cours de piano collectif en presentiel (1h)",
}
START_AT = datetime(2026, 9, 12, tzinfo=timezone.utc)
END_AT_EXCLUSIVE = datetime(2027, 6, 20, tzinfo=timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lock Liam-Jonathan Ango's explicitly retained EUR 22 booking prices after reorganization."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, dry-run only.")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == TARGET_USER_ID).with_for_update())
        if user is None or user.first_name != "Liam-Jonathan" or user.last_name != "Ango":
            raise SystemExit(f"[{SCRIPT_PREFIX}] target_user_mismatch")

        rows = db.execute(
            select(Booking, CourseSession, CourseType)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .where(
                Booking.user_id == TARGET_USER_ID,
                Booking.client_plan_subscription_id == TARGET_SUBSCRIPTION_ID,
                Booking.status == BookingStatus.BOOKED,
                Booking.total_incl_vat_snapshot == TARGET_PRICE,
                CourseSession.start_at_utc >= START_AT,
                CourseSession.start_at_utc < END_AT_EXCLUSIVE,
                CourseType.name.in_(TARGET_COURSE_TYPE_NAMES),
            )
            .order_by(CourseSession.start_at_utc)
            .with_for_update()
        ).all()
        if len(rows) != TARGET_BOOKING_COUNT:
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] expected_booking_count={TARGET_BOOKING_COUNT} found={len(rows)}"
            )

        booking_ids = {booking.id for booking, _, _ in rows}
        invoice_line_count = int(
            db.scalar(
                select(func.count(ClientInvoiceLine.id)).where(
                    ClientInvoiceLine.source == "BOOKING",
                    ClientInvoiceLine.source_payment_id.in_(booking_ids),
                )
            )
            or 0
        )
        if invoice_line_count:
            raise SystemExit(f"[{SCRIPT_PREFIX}] invoiced_booking_count={invoice_line_count}")

        unlocked = [booking for booking, _, _ in rows if not booking.pricing_snapshot_locked]
        print(f"[{SCRIPT_PREFIX}] mode={'apply' if args.apply else 'dry-run'}")
        print(
            f"[{SCRIPT_PREFIX}] user={user.id}|bookings={len(rows)}|unlocked={len(unlocked)}|"
            f"price={TARGET_PRICE:.2f}|invoice_lines={invoice_line_count}"
        )
        print(
            f"[{SCRIPT_PREFIX}] period={rows[0][1].start_at_utc.isoformat()}->"
            f"{rows[-1][1].start_at_utc.isoformat()}"
        )

        if args.apply:
            for booking in unlocked:
                booking.pricing_snapshot_locked = True
                db.add(booking)
            db.commit()
            print(f"[{SCRIPT_PREFIX}] committed=true|updated={len(unlocked)}")
        else:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")


if __name__ == "__main__":
    main()
