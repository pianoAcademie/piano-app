from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.admin_clients import _build_admin_client_payments
from app.api.routes.quotes import _quote_transformation_execution
from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.models.user import User


def money(value: object | None) -> str:
    return f"{Decimal(value or 0).quantize(Decimal('0.01')):.2f}"


def ids(values: object) -> list[UUID]:
    out: list[UUID] = []
    if not isinstance(values, list):
        return out
    for value in values:
        try:
            out.append(UUID(str(value)))
        except (TypeError, ValueError):
            pass
    return out


def main() -> None:
    with SessionLocal() as db:
        location = db.scalar(select(Location).where(Location.name.ilike("%bar%duc%")))
        if location is None:
            raise SystemExit("Bar-le-Duc location missing")

        booking_source: dict[UUID, tuple[Quote, UUID]] = {}
        quote_lines: dict[UUID, list[QuoteLine]] = {}
        billing_ids: set[UUID] = set()
        followups = list(db.scalars(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.status == "completed")).all())
        for followup in followups:
            quote = db.get(Quote, followup.quote_id)
            if quote is None or quote.school_year_label != "2026-2027":
                continue
            execution = _quote_transformation_execution(followup)
            if execution.get("status") != "executed":
                continue
            try:
                billing_id = UUID(str(execution.get("billing_client_id")))
            except (TypeError, ValueError):
                continue
            booking_ids = ids(execution.get("created_booking_ids"))
            if not booking_ids:
                continue
            billing_ids.add(billing_id)
            for booking_id in booking_ids:
                booking_source[booking_id] = (quote, billing_id)

        effective_by_booking: dict[UUID, Decimal] = {}
        for billing_id in billing_ids:
            for payment in _build_admin_client_payments(db, client_id=billing_id):
                if payment.source == "BOOKING":
                    effective_by_booking[payment.id] = Decimal(payment.total_incl_vat)

        rows = list(
            db.execute(
                select(Booking, CourseSession, CourseType, User)
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .join(CourseType, CourseType.id == CourseSession.course_type_id)
                .join(User, User.id == Booking.user_id)
                .where(
                    Booking.id.in_(list(booking_source)),
                    CourseSession.location_id == location.id,
                    Booking.status == BookingStatus.BOOKED,
                )
                .order_by(User.last_name.asc(), User.first_name.asc(), CourseSession.start_at_utc.asc())
            ).all()
        )

        groups: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
        price_distribution = Counter()
        mismatch_count = 0
        for booking, session, course_type, user in rows:
            effective = effective_by_booking.get(booking.id, Decimal(booking.total_incl_vat_snapshot or 0))
            stored = Decimal(booking.total_incl_vat_snapshot or 0)
            quote, billing_id = booking_source[booking.id]
            price_distribution[(money(stored), money(effective))] += 1
            if stored == effective:
                continue
            mismatch_count += 1
            key = (quote.quote_number, str(user.id), course_type.name, money(stored), money(effective))
            group = groups.setdefault(
                key,
                {
                    "quote_number": quote.quote_number,
                    "student": " ".join(x for x in (user.first_name, user.last_name) if x).strip() or user.email,
                    "course_type": course_type.name,
                    "quote_booking_price_ttc": money(stored),
                    "account_display_price_ttc": money(effective),
                    "booking_count": 0,
                    "pricing_locked": bool(booking.pricing_snapshot_locked),
                    "first_session": session.start_at_utc.date().isoformat(),
                    "last_session": session.start_at_utc.date().isoformat(),
                    "quote_total_ttc": money(quote.total_ttc),
                    "quote_service_lines": [],
                },
            )
            group["booking_count"] = int(group["booking_count"]) + 1
            group["last_session"] = session.start_at_utc.date().isoformat()
            if not group["quote_service_lines"]:
                lines = quote_lines.setdefault(
                    quote.id,
                    list(
                        db.scalars(
                            select(QuoteLine)
                            .where(
                                QuoteLine.quote_id == quote.id,
                                QuoteLine.line_category == "service",
                                QuoteLine.line_type == "item",
                            )
                            .order_by(QuoteLine.sort_order.asc())
                        ).all()
                    ),
                )
                group["quote_service_lines"] = [
                    {
                        "title": line.title,
                        "quantity": money(line.quantity),
                        "unit_ttc": money(line.unit_price_ttc),
                        "amount_ttc": money(line.amount_ttc),
                    }
                    for line in lines
                ]

        print(
            json.dumps(
                {
                    "active_quote_bookings_checked": len(rows),
                    "mismatched_active_bookings": mismatch_count,
                    "price_distribution_quote_to_account": {
                        f"{stored}->{effective}": count
                        for (stored, effective), count in sorted(price_distribution.items())
                    },
                    "mismatch_groups": list(groups.values()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
