from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.quotes import _quote_transformation_execution
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, Location
from app.models.client_record import ClientInvoiceLine, PaymentReceipt
from app.models.quote import Quote, QuoteAcceptanceFollowup
from app.models.user import User


SCRIPT_PREFIX = "PROD_REPAIR_BAR_LE_DUC_QUOTE_BOOKING_PRICE_LOCKS"
SCHOOL_YEAR = "2026-2027"
LOCATION_PATTERN = "%bar%duc%"


def _uuid_list(values: object) -> list[UUID]:
    parsed: list[UUID] = []
    if not isinstance(values, list):
        return parsed
    for value in values:
        try:
            parsed.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return parsed


def _money(value: object | None) -> str:
    return f"{Decimal(value or 0).quantize(Decimal('0.01')):.2f}"


def _student_label(user: User) -> str:
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or user.email


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Lock the accepted quote price on quote-created Bar-le-Duc bookings. "
            "This is a direct database repair and deliberately emits no notifications."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag, dry-run only.")
    args = parser.parse_args()

    with SessionLocal() as db:
        locations = list(db.scalars(select(Location).where(Location.name.ilike(LOCATION_PATTERN))).all())
        location_ids = {location.id for location in locations}
        if not location_ids:
            raise SystemExit(f"[{SCRIPT_PREFIX}] bar_le_duc_location_not_found")

        booking_quote_number: dict[UUID, str] = {}
        duplicate_execution_links: dict[UUID, list[str]] = {}
        executed_quote_count = 0
        followup_rows = db.execute(
            select(Quote, QuoteAcceptanceFollowup)
            .join(QuoteAcceptanceFollowup, QuoteAcceptanceFollowup.quote_id == Quote.id)
            .where(Quote.school_year_label == SCHOOL_YEAR)
            .order_by(Quote.created_at.asc(), Quote.id.asc())
        ).all()
        for quote, followup in followup_rows:
            execution = _quote_transformation_execution(followup)
            if str(execution.get("status") or "").strip().lower() != "executed":
                continue
            booking_ids = _uuid_list(execution.get("created_booking_ids"))
            if not booking_ids:
                continue
            executed_quote_count += 1
            for booking_id in booking_ids:
                previous = booking_quote_number.get(booking_id)
                if previous is not None and previous != quote.quote_number:
                    duplicate_execution_links.setdefault(booking_id, [previous]).append(quote.quote_number)
                else:
                    booking_quote_number[booking_id] = quote.quote_number

        if duplicate_execution_links:
            raise SystemExit(
                f"[{SCRIPT_PREFIX}] duplicate_quote_execution_booking_links={len(duplicate_execution_links)}"
            )
        if not booking_quote_number:
            raise SystemExit(f"[{SCRIPT_PREFIX}] no_executed_quote_bookings")

        rows = list(
            db.execute(
                select(Booking, CourseSession, User)
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .join(User, User.id == Booking.user_id)
                .where(
                    Booking.id.in_(list(booking_quote_number)),
                    CourseSession.location_id.in_(location_ids),
                )
                .order_by(User.last_name.asc(), User.first_name.asc(), CourseSession.start_at_utc.asc())
            ).all()
        )
        if not rows:
            raise SystemExit(f"[{SCRIPT_PREFIX}] no_bar_le_duc_quote_bookings")

        target_ids = {booking.id for booking, _, _ in rows}
        invoice_lines = list(
            db.scalars(
                select(ClientInvoiceLine).where(
                    ClientInvoiceLine.source == "BOOKING",
                    ClientInvoiceLine.source_payment_id.in_(target_ids),
                )
            ).all()
        )
        receipts = list(db.scalars(select(PaymentReceipt).where(PaymentReceipt.booking_id.in_(target_ids))).all())
        protected_ids = {
            *(line.source_payment_id for line in invoice_lines),
            *(receipt.booking_id for receipt in receipts),
        }

        eligible_rows = [row for row in rows if row[0].id not in protected_ids]
        locked_rows = [row for row in eligible_rows if bool(row[0].pricing_snapshot_locked)]
        unlocked_rows = [row for row in eligible_rows if not bool(row[0].pricing_snapshot_locked)]
        protected_rows = [row for row in rows if row[0].id in protected_ids]

        price_counts = Counter(_money(booking.total_incl_vat_snapshot) for booking, _, _ in unlocked_rows)
        student_counts = Counter(_student_label(user) for _, _, user in unlocked_rows)
        aydin_rows = [
            row
            for row in rows
            if "aydin" in _student_label(row[2]).casefold()
        ]

        print(f"[{SCRIPT_PREFIX}] mode={'apply' if args.apply else 'dry-run'}")
        print(
            f"[{SCRIPT_PREFIX}] school_year={SCHOOL_YEAR}|locations={','.join(sorted(row.name for row in locations))}|"
            f"executed_quotes={executed_quote_count}|bar_le_duc_bookings={len(rows)}"
        )
        print(
            f"[{SCRIPT_PREFIX}] eligible={len(eligible_rows)}|already_locked={len(locked_rows)}|"
            f"to_lock={len(unlocked_rows)}|protected={len(protected_rows)}|"
            f"invoice_lines={len(invoice_lines)}|payment_receipts={len(receipts)}"
        )
        print(f"[{SCRIPT_PREFIX}] to_lock_price_distribution={dict(sorted(price_counts.items()))}")
        print(f"[{SCRIPT_PREFIX}] affected_students={len(student_counts)}")
        print(
            f"[{SCRIPT_PREFIX}] aydin_bookings={len(aydin_rows)}|"
            f"aydin_prices={dict(sorted(Counter(_money(row[0].total_incl_vat_snapshot) for row in aydin_rows).items()))}"
        )
        if protected_rows:
            protected_quotes = sorted({booking_quote_number[row[0].id] for row in protected_rows})
            print(f"[{SCRIPT_PREFIX}] protected_quotes={protected_quotes}")

        if args.apply:
            locked_count = 0
            for booking, _, _ in unlocked_rows:
                # The stored snapshot was computed from the accepted quote during
                # transformation. Locking it prevents later catalogue changes from
                # silently replacing that contractual price in the client account.
                booking.pricing_snapshot_locked = True
                db.add(booking)
                locked_count += 1
            db.flush()
            remaining_unlocked = list(
                db.scalars(
                    select(Booking.id).where(
                        Booking.id.in_([row[0].id for row in eligible_rows]),
                        Booking.pricing_snapshot_locked.is_(False),
                    )
                ).all()
            )
            if remaining_unlocked:
                raise SystemExit(f"[{SCRIPT_PREFIX}] verification_failed_unlocked={len(remaining_unlocked)}")
            db.commit()
            print(f"[{SCRIPT_PREFIX}] committed=true|updated={locked_count}")
        else:
            db.rollback()
            print(f"[{SCRIPT_PREFIX}] committed=false")

        print(f"[{SCRIPT_PREFIX}] student_notifications=0|notification_side_effects=disabled")


if __name__ == "__main__":
    main()
