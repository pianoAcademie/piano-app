from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.quotes import _quote_transformation_execution
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession, CourseType, Location
from app.models.client_record import ClientManualTransaction
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.models.user import User


SCHOOL_YEAR = "2026-2027"
LOCATION_TOKEN = "bar-le-duc"


def money(value: object | None) -> str:
    return f"{Decimal(value or 0).quantize(Decimal('0.01')):.2f}"


def uuid_list(values: object) -> list[UUID]:
    out: list[UUID] = []
    if not isinstance(values, list):
        return out
    for value in values:
        try:
            out.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return out


def user_label(user: User | None) -> str | None:
    if user is None:
        return None
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or user.email


def main() -> None:
    with SessionLocal() as db:
        locations = list(db.scalars(select(Location).where(Location.name.ilike("%bar%duc%"))).all())
        location_ids = {row.id for row in locations}

        quote_rows = list(
            db.scalars(
                select(Quote)
                .where(Quote.school_year_label == SCHOOL_YEAR)
                .order_by(Quote.created_at.asc(), Quote.quote_number.asc())
            ).all()
        )

        booking_to_quote: dict[UUID, str] = {}
        quote_results: list[dict[str, object]] = []
        for quote in quote_rows:
            lines = list(
                db.scalars(
                    select(QuoteLine)
                    .where(QuoteLine.quote_id == quote.id)
                    .order_by(QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
                ).all()
            )
            searchable = json.dumps(
                {
                    "location_id": str(quote.location_id or ""),
                    "calendar_snapshot": quote.calendar_snapshot,
                    "lines": [{"title": line.title, "description": line.description, "meta": line.meta} for line in lines],
                },
                ensure_ascii=False,
                default=str,
            ).casefold()
            if quote.location_id not in location_ids and LOCATION_TOKEN not in searchable:
                continue

            followup = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == quote.id))
            execution = _quote_transformation_execution(followup) if followup is not None else {}
            booking_ids = uuid_list(execution.get("created_booking_ids"))
            transaction_ids = uuid_list(execution.get("created_transaction_ids"))
            for booking_id in booking_ids:
                booking_to_quote[booking_id] = quote.quote_number

            bookings = (
                list(db.scalars(select(Booking).where(Booking.id.in_(booking_ids))).all())
                if booking_ids
                else []
            )
            transactions = (
                list(
                    db.scalars(
                        select(ClientManualTransaction).where(ClientManualTransaction.id.in_(transaction_ids))
                    ).all()
                )
                if transaction_ids
                else []
            )
            booking_price_counts = Counter(money(row.total_incl_vat_snapshot) for row in bookings)
            booking_total = sum((Decimal(row.total_incl_vat_snapshot or 0) for row in bookings), Decimal("0"))
            transaction_total = sum((Decimal(row.total_incl_vat or 0) for row in transactions), Decimal("0"))
            student = db.get(User, UUID(str(execution["student_client_id"]))) if execution.get("student_client_id") else None
            billing = db.get(User, UUID(str(execution["billing_client_id"]))) if execution.get("billing_client_id") else None

            service_lines = [
                {
                    "title": line.title,
                    "quantity": money(line.quantity),
                    "unit_ttc": money(line.unit_price_ttc),
                    "amount_ttc": money(line.amount_ttc),
                    "activity_id": str(line.activity_id) if line.activity_id else None,
                    "schedule_key": str((line.meta or {}).get("schedule_key") or "") or None,
                }
                for line in lines
                if line.line_category == "service" and line.line_type == "item"
            ]
            quote_results.append(
                {
                    "quote_number": quote.quote_number,
                    "status": quote.status,
                    "created_at": quote.created_at.isoformat(),
                    "student": user_label(student),
                    "billing": user_label(billing),
                    "quote_total": money(quote.total_ttc),
                    "followup_status": followup.status if followup is not None else None,
                    "execution_status": execution.get("status"),
                    "service_lines": service_lines,
                    "created_booking_count": len(bookings),
                    "booking_price_counts": dict(sorted(booking_price_counts.items())),
                    "booking_total": money(booking_total),
                    "created_transaction_count": len(transactions),
                    "transaction_total": money(transaction_total),
                    "generated_total": money(booking_total + transaction_total),
                    "delta_vs_quote": money(booking_total + transaction_total - Decimal(quote.total_ttc or 0)),
                }
            )

        session_rows = list(
            db.execute(
                select(Booking, CourseSession, CourseType, User)
                .join(CourseSession, CourseSession.id == Booking.session_id)
                .join(CourseType, CourseType.id == CourseSession.course_type_id)
                .join(User, User.id == Booking.user_id)
                .where(CourseSession.location_id.in_(location_ids))
                .order_by(User.last_name.asc(), User.first_name.asc(), CourseSession.start_at_utc.asc())
            ).all()
        )
        account_groups: dict[tuple[str, str, str], dict[str, object]] = {}
        orphan_quote_booking_ids: list[str] = []
        for booking, session, course_type, user in session_rows:
            key = (str(user.id), course_type.name, money(booking.total_incl_vat_snapshot))
            row = account_groups.setdefault(
                key,
                {
                    "student": user_label(user),
                    "email": user.email,
                    "course_type": course_type.name,
                    "booking_price_ttc": money(booking.total_incl_vat_snapshot),
                    "count": 0,
                    "statuses": Counter(),
                    "source_quotes": set(),
                    "first_session": session.start_at_utc.date().isoformat(),
                    "last_session": session.start_at_utc.date().isoformat(),
                },
            )
            row["count"] = int(row["count"]) + 1
            row["statuses"][booking.status.value] += 1
            row["last_session"] = session.start_at_utc.date().isoformat()
            if booking.id in booking_to_quote:
                row["source_quotes"].add(booking_to_quote[booking.id])
            elif booking.client_plan_subscription_id is not None and Decimal(booking.total_incl_vat_snapshot or 0) > 0:
                orphan_quote_booking_ids.append(str(booking.id))

        account_results: list[dict[str, object]] = []
        for row in account_groups.values():
            row["statuses"] = dict(sorted(row["statuses"].items()))
            row["source_quotes"] = sorted(row["source_quotes"])
            account_results.append(row)

        print(
            json.dumps(
                {
                    "school_year": SCHOOL_YEAR,
                    "locations": [{"id": str(row.id), "name": row.name} for row in locations],
                    "quotes": quote_results,
                    "accounts": account_results,
                    "positive_subscription_bookings_without_quote_execution_link": orphan_quote_booking_ids,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


if __name__ == "__main__":
    main()
