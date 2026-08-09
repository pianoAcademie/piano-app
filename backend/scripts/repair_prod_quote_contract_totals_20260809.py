from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import os
import sys
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.models.catalog import Booking, BookingStatus, CourseSession
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, PaymentReceipt
from app.models.plan import ClientForfaitActivityPricing
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.services.reminders import ensure_booking_reminder


SCRIPT_PREFIX = "PROD_QUOTE_CONTRACT_TOTALS_20260809"
DRIFT_TTC = Decimal("2.00")

BOOKING_SERIES_TARGETS = (
    # quote, subscription, recurrence group, expected booked total TTC
    ("DV-20260626132925-1F08", "c812179f-fa1a-45e2-a5b3-2904458c3bf2", "7eb35504-62f7-423e-b301-7d6472f7fcd9", Decimal("1122.00")),
    ("DV-20260626132925-1F08", "c812179f-fa1a-45e2-a5b3-2904458c3bf2", "48540e1d-b341-511e-b875-00d0f7cfa311", Decimal("928.00")),
    ("DV-20260614090415-1F43", "aba58b9f-a6c7-4678-be83-aca4ae4c899c", "310cec40-83e9-5bc8-9afe-fda5d503ad41", Decimal("1122.00")),
    ("DV-20260614090415-1F43", "aba58b9f-a6c7-4678-be83-aca4ae4c899c", "b5044d75-4588-5e09-b0d3-683a944cf019", Decimal("928.00")),
    ("DV-20260625081924-40AC", "b2b0318c-27fd-4c48-97fb-ac6ee384d09f", "fcc5f272-497a-4c07-8ba8-061dde804093", Decimal("704.00")),
)

MISSING_PRIMARY_QUOTE = "DV-20260624081822-D6C2"
MISSING_PRIMARY_SERIES = UUID("262305f6-04ff-522d-a3ab-82e1968656d5")
MISSING_PRIMARY_TOTAL = Decimal("1216.00")
MISSING_PRIMARY_COUNT = 32
FLAT_DISCOUNT_QUOTE = "DV-20260609094129-6973"


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _split_amount(total: Decimal, count: int) -> list[Decimal]:
    base = _q2(total / Decimal(count))
    parts = [base for _ in range(count)]
    parts[-1] = _q2(parts[-1] + total - sum(parts, Decimal("0.00")))
    return parts


def _split_vat(total_ttc: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    divisor = Decimal("1.00") + (vat_rate / Decimal("100.00"))
    amount_ht = _q2(total_ttc / divisor) if divisor > Decimal("0.00") else total_ttc
    return amount_ht, _q2(total_ttc - amount_ht)


def _drift_rows(db):
    return db.execute(
        text(
            """
            WITH integrated AS (
              SELECT q.id quote_id,q.quote_number,q.approved_at,f.target_client_id,
                     sub_id.value::uuid subscription_id
              FROM quotes q
              JOIN quote_acceptance_followups f ON f.quote_id=q.id AND f.status='completed'
              CROSS JOIN LATERAL jsonb_array_elements_text(
                COALESCE(f.payload->'quote_to_enrollment_execution'->'created_subscription_ids','[]'::jsonb)
              ) sub_id(value)
              WHERE q.status='approved'
                AND f.payload->'quote_to_enrollment_execution'->>'status'='executed'
            ), service AS (
              SELECT i.*,ql.activity_id,
                     SUM(ql.amount_ttc) service_ttc,
                     SUM(ql.quantity * COALESCE(NULLIF(ql.duration_minutes,0),ct.duration_minutes) / 60.0) service_hours,
                     ROW_NUMBER() OVER (
                       PARTITION BY i.subscription_id,ql.activity_id
                       ORDER BY i.approved_at DESC NULLS LAST,i.quote_id DESC
                     ) rn
              FROM integrated i
              JOIN quote_lines ql ON ql.quote_id=i.quote_id
              JOIN course_types ct ON ct.id=ql.activity_id
              WHERE ql.line_category='service' AND ql.line_type='item'
                AND ql.activity_id IS NOT NULL AND ql.amount_ttc>0
              GROUP BY i.quote_id,i.quote_number,i.approved_at,i.target_client_id,
                       i.subscription_id,ql.activity_id
            ), audit AS (
              SELECT s.subscription_id,s.activity_id,s.quote_number,
                     concat_ws(' ',u.first_name,u.last_name) client,
                     COALESCE(p.loyalty_discount_per_hour_ttc,0) loyalty,
                     COALESCE(p.second_course_weekly_discount_per_hour_ttc,0) second_discount,
                     ROUND(
                       (CASE WHEN ct.default_course_rate_ttc IS NOT NULL
                         THEN ct.default_course_rate_ttc/(ct.duration_minutes/60.0)
                         ELSE ct.default_hourly_rate END)
                       -COALESCE(p.loyalty_discount_per_hour_ttc,0)
                       +COALESCE(p.short_commitment_supplement_per_hour_ttc,0)
                       -(s.service_ttc/s.service_hours),2
                     ) drift
              FROM service s
              JOIN client_plan_subscriptions cps ON cps.id=s.subscription_id AND cps.status='ACTIVE'
              JOIN users u ON u.id=s.target_client_id
              JOIN course_types ct ON ct.id=s.activity_id
              LEFT JOIN client_forfait_activity_pricing p
                ON p.subscription_id=s.subscription_id AND p.course_type_id=s.activity_id
              WHERE s.rn=1
            )
            SELECT * FROM audit WHERE drift=:drift ORDER BY client,quote_number
            """
        ),
        {"drift": DRIFT_TTC},
    ).mappings().all()


def _repair_pricing_drift(db, *, apply: bool) -> tuple[int, int]:
    rows = _drift_rows(db)
    if len(rows) != 135:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected_pricing_drift_count={len(rows)} expected=135")
    inserted = 0
    updated = 0
    now = datetime.now(timezone.utc)
    for row in rows:
        pricing = db.scalar(
            select(ClientForfaitActivityPricing)
            .where(
                ClientForfaitActivityPricing.subscription_id == row["subscription_id"],
                ClientForfaitActivityPricing.course_type_id == row["activity_id"],
            )
            .with_for_update()
            .limit(1)
        )
        if pricing is None:
            inserted += 1
            if apply:
                db.add(
                    ClientForfaitActivityPricing(
                        subscription_id=row["subscription_id"],
                        course_type_id=row["activity_id"],
                        loyalty_discount_per_hour_ttc=DRIFT_TTC,
                        family_discount_per_hour_ttc=Decimal("0.00"),
                        short_commitment_supplement_per_hour_ttc=Decimal("0.00"),
                        second_course_weekly_discount_per_hour_ttc=Decimal("0.00"),
                        updated_at=now,
                    )
                )
            continue
        updated += 1
        if not apply:
            continue
        pricing.loyalty_discount_per_hour_ttc = _q2(
            Decimal(pricing.loyalty_discount_per_hour_ttc or 0) + DRIFT_TTC
        )
        if Decimal(pricing.second_course_weekly_discount_per_hour_ttc or 0) > Decimal("0.00"):
            pricing.second_course_weekly_discount_per_hour_ttc = _q2(
                Decimal(pricing.second_course_weekly_discount_per_hour_ttc or 0) + DRIFT_TTC
            )
        pricing.updated_at = now
        db.add(pricing)
    return inserted, updated


def _repair_booking_series(db, *, apply: bool) -> int:
    changed = 0
    for quote_number, subscription_raw, group_raw, expected_total in BOOKING_SERIES_TARGETS:
        subscription_id = UUID(subscription_raw)
        group_id = UUID(group_raw)
        rows = db.execute(
            select(Booking, CourseSession)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(
                Booking.client_plan_subscription_id == subscription_id,
                Booking.status == BookingStatus.BOOKED,
                CourseSession.recurrence_group_id == group_id,
            )
            .with_for_update()
            .order_by(CourseSession.start_at_utc.asc(), Booking.id.asc())
        ).all()
        if not rows:
            raise SystemExit(f"[{SCRIPT_PREFIX}] no_bookings quote={quote_number} group={group_id}")
        booking_ids = [booking.id for booking, _ in rows]
        invoice_line = db.scalar(
            select(ClientInvoiceLine.id).where(
                ClientInvoiceLine.source == "BOOKING",
                ClientInvoiceLine.source_payment_id.in_(booking_ids),
            ).limit(1)
        )
        finalized_receipt = db.scalar(
            select(PaymentReceipt.id).where(
                PaymentReceipt.booking_id.in_(booking_ids),
                (PaymentReceipt.final_invoice_note_id.is_not(None)) | (PaymentReceipt.status != "PENDING"),
            ).limit(1)
        )
        if invoice_line is not None or finalized_receipt is not None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] billed_booking_guard quote={quote_number} group={group_id}")

        before = _q2(sum((Decimal(booking.total_incl_vat_snapshot or 0) for booking, _ in rows), Decimal("0.00")))
        expected_parts = _split_amount(expected_total, len(rows))
        print(
            f"[{SCRIPT_PREFIX}] series quote={quote_number} group={group_id} "
            f"count={len(rows)} before={before} after={expected_total}"
        )
        for (booking, _), expected_ttc in zip(rows, expected_parts):
            current_ttc = _q2(Decimal(booking.total_incl_vat_snapshot or 0))
            if current_ttc == expected_ttc:
                continue
            changed += 1
            if not apply:
                continue
            vat_rate = Decimal(booking.vat_rate_snapshot or 0)
            amount_ht, vat_amount = _split_vat(expected_ttc, vat_rate)
            booking.price_excl_vat_snapshot = amount_ht
            booking.vat_amount_snapshot = vat_amount
            booking.total_incl_vat_snapshot = expected_ttc
            db.add(booking)
    return changed


def _create_missing_primary_bookings(db, *, apply: bool) -> int:
    quote = db.scalar(select(Quote).where(Quote.quote_number == MISSING_PRIMARY_QUOTE).limit(1))
    if quote is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] missing_quote={MISSING_PRIMARY_QUOTE}")
    followup = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == quote.id).limit(1))
    if followup is None or followup.target_client_id is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] missing_followup={MISSING_PRIMARY_QUOTE}")
    execution = (followup.payload or {}).get("quote_to_enrollment_execution") or {}
    subscription_ids = execution.get("created_subscription_ids") or []
    if len(subscription_ids) != 1:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected_subscription_count={len(subscription_ids)}")
    subscription_id = UUID(str(subscription_ids[0]))

    snapshot_sessions = [
        item for item in (quote.calendar_snapshot or {}).get("sessions", [])
        if str(item.get("series_key") or "") == str(MISSING_PRIMARY_SERIES)
    ]
    expected_dates = {str(item.get("date") or "") for item in snapshot_sessions}
    if len(expected_dates) != MISSING_PRIMARY_COUNT:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected_snapshot_dates={len(expected_dates)}")
    sessions = db.scalars(
        select(CourseSession)
        .where(CourseSession.recurrence_group_id == MISSING_PRIMARY_SERIES)
        .order_by(CourseSession.start_at_utc.asc())
    ).all()
    sessions = [session for session in sessions if session.start_at_utc.astimezone(timezone.utc).date().isoformat() in expected_dates]
    if len(sessions) != MISSING_PRIMARY_COUNT:
        raise SystemExit(f"[{SCRIPT_PREFIX}] unexpected_live_sessions={len(sessions)}")

    existing = db.scalars(
        select(Booking).where(
            Booking.user_id == followup.target_client_id,
            Booking.session_id.in_([session.id for session in sessions]),
        )
    ).all()
    if existing:
        if len(existing) == MISSING_PRIMARY_COUNT and all(row.status == BookingStatus.BOOKED for row in existing):
            return 0
        raise SystemExit(f"[{SCRIPT_PREFIX}] conflicting_existing_bookings={len(existing)}")

    print(
        f"[{SCRIPT_PREFIX}] missing_primary quote={MISSING_PRIMARY_QUOTE} "
        f"count={len(sessions)} total={MISSING_PRIMARY_TOTAL}"
    )
    if not apply:
        return len(sessions)
    now = datetime.now(timezone.utc)
    created_ids: list[str] = []
    for session, total_ttc in zip(sessions, _split_amount(MISSING_PRIMARY_TOTAL, len(sessions))):
        booked_count = db.scalar(
            select(func.count(Booking.id)).where(
                Booking.session_id == session.id,
                Booking.status == BookingStatus.BOOKED,
            )
        ) or 0
        if int(booked_count) >= int(session.capacity_max or 0):
            raise SystemExit(f"[{SCRIPT_PREFIX}] full_session={session.id}")
        amount_ht, vat_amount = _split_vat(total_ttc, Decimal("20.00"))
        booking = Booking(
            session_id=session.id,
            user_id=followup.target_client_id,
            client_plan_subscription_id=subscription_id,
            status=BookingStatus.BOOKED,
            booked_at=now,
            price_excl_vat_snapshot=amount_ht,
            vat_rate_snapshot=Decimal("20.00"),
            vat_amount_snapshot=vat_amount,
            total_incl_vat_snapshot=total_ttc,
            currency_snapshot=(quote.currency or "EUR").upper(),
        )
        db.add(booking)
        db.flush()
        ensure_booking_reminder(db, booking=booking, session_obj=session, now=now)
        created_ids.append(str(booking.id))
    next_execution = dict(execution)
    next_execution["created_booking_ids"] = [*(execution.get("created_booking_ids") or []), *created_ids]
    next_payload = dict(followup.payload or {})
    next_payload["quote_to_enrollment_execution"] = next_execution
    followup.payload = next_payload
    db.add(followup)
    return len(created_ids)


def _create_missing_flat_discount(db, *, apply: bool) -> int:
    quote = db.scalar(select(Quote).where(Quote.quote_number == FLAT_DISCOUNT_QUOTE).limit(1))
    if quote is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] missing_quote={FLAT_DISCOUNT_QUOTE}")
    discount_line = db.scalar(
        select(QuoteLine).where(
            QuoteLine.quote_id == quote.id,
            QuoteLine.line_type == "discount",
            QuoteLine.amount_ttc == Decimal("-2.00"),
        ).limit(1)
    )
    if discount_line is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] missing_flat_discount_line")
    reference = f"QUOTE:{quote.id}:ROW:extra-{discount_line.id}"
    existing = db.scalar(select(ClientManualTransaction).where(ClientManualTransaction.reference == reference).limit(1))
    if existing is not None:
        return 0
    followup = db.scalar(select(QuoteAcceptanceFollowup).where(QuoteAcceptanceFollowup.quote_id == quote.id).limit(1))
    if followup is None or followup.target_client_id is None:
        raise SystemExit(f"[{SCRIPT_PREFIX}] missing_flat_discount_followup")
    resolution = ((followup.payload or {}).get("quote_to_enrollment") or {}).get("clientResolution") or {}
    billing_id = UUID(str(resolution.get("selectedClientId")))
    print(f"[{SCRIPT_PREFIX}] flat_discount quote={FLAT_DISCOUNT_QUOTE} amount=-2.00 billing={billing_id}")
    if not apply:
        return 1
    db.add(
        ClientManualTransaction(
            user_id=billing_id,
            student_user_id=followup.target_client_id,
            actor_user_id=None,
            transaction_type="DISCOUNT",
            status="COMPLETED",
            label="Remise fidélité",
            description=f"Régularisation transformation devis {quote.quote_number}",
            category="Remise",
            occurred_at=datetime.now(timezone.utc),
            amount_excl_vat=Decimal("-1.67"),
            vat_rate=Decimal("20.000"),
            vat_amount=Decimal("-0.33"),
            total_incl_vat=Decimal("-2.00"),
            currency=(quote.currency or "EUR").upper(),
            reference=reference,
            legal_entity_id=quote.legal_entity_id,
        )
    )
    return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        inserted, updated = _repair_pricing_drift(db, apply=args.apply)
        changed_bookings = _repair_booking_series(db, apply=args.apply)
        created_primary = _create_missing_primary_bookings(db, apply=args.apply)
        created_discount = _create_missing_flat_discount(db, apply=args.apply)
        if args.apply:
            db.commit()
            remaining = len(_drift_rows(db))
            if remaining:
                raise SystemExit(f"[{SCRIPT_PREFIX}] remaining_pricing_drift={remaining}")
        else:
            db.rollback()
        print(
            f"[{SCRIPT_PREFIX}] summary mode={'apply' if args.apply else 'dry-run'} "
            f"pricing_inserted={inserted} pricing_updated={updated} "
            f"bookings_changed={changed_bookings} primary_created={created_primary} "
            f"flat_discounts_created={created_discount}"
        )


if __name__ == "__main__":
    main()
