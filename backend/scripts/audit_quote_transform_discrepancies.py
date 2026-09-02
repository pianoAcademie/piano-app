from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession
from app.services.quote_planning_audit import (
    ACTIVE_BOOKING_STATUSES,
    AuditCandidate,
    _audit_candidates,
    _execution,
    _json_list,
    _parse_uuid,
    _zone,
)


PARIS = ZoneInfo("Europe/Paris")
def _parse_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _month_end(value: date) -> date:
    if value.month == 12:
        return date(value.year, 12, 31)
    return date(value.year, value.month + 1, 1) - timedelta(days=1)


def _local_signature(session_obj: CourseSession) -> tuple[UUID, UUID, int, str, str]:
    zone = _zone(session_obj.timezone)
    local_start = session_obj.start_at_utc.astimezone(zone)
    local_end = session_obj.end_at_utc.astimezone(zone)
    return (
        session_obj.course_type_id,
        session_obj.location_id,
        local_start.weekday(),
        local_start.strftime("%H:%M"),
        local_end.strftime("%H:%M"),
    )


def _active_booking(booking: Booking) -> bool:
    return booking.status in ACTIVE_BOOKING_STATUSES


def _candidate_missing_invoice_dates(candidate: AuditCandidate) -> list[date]:
    return sorted(
        candidate.sessions_by_booking_id[booking.id]
        .start_at_utc.astimezone(_zone(candidate.sessions_by_booking_id[booking.id].timezone))
        .date()
        for booking in candidate.bookings
        if not candidate.invoice_lines_by_booking_id.get(booking.id)
    )


def _classification_row(
    db,
    *,
    candidate: AuditCandidate,
    today: date,
) -> dict[str, Any]:
    execution = _execution(candidate.followup)
    executed_at = _parse_datetime(execution.get("executed_at"))
    created_booking_ids = [
        parsed
        for value in _json_list(execution.get("created_booking_ids"))
        if (parsed := _parse_uuid(value)) is not None
    ]
    all_booking_rows = list(
        db.execute(
            select(Booking, CourseSession)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .where(Booking.id.in_(created_booking_ids))
        ).all()
    ) if created_booking_ids else []

    signature = _local_signature(candidate.template)
    related_rows = [
        (booking, session_obj)
        for booking, session_obj in all_booking_rows
        if booking.user_id == candidate.student.id and _local_signature(session_obj) == signature
    ]
    related_active_rows = [(booking, session_obj) for booking, session_obj in related_rows if _active_booking(booking)]
    related_dates = {
        session_obj.start_at_utc.astimezone(_zone(session_obj.timezone)).date()
        for _, session_obj in related_active_rows
    }
    related_series_ids = {
        session_obj.recurrence_group_id
        for _, session_obj in related_active_rows
        if session_obj.recurrence_group_id is not None
    }

    evidence: list[str] = []
    remaining_codes = list(candidate.issue_codes)
    false_codes: list[str] = []
    posterior_codes: list[str] = []

    monthly_card = str(execution.get("annual_invoice_skipped_reason") or "").strip().upper() == "MONTHLY_CARD_BILLING"
    missing_invoice_dates = _candidate_missing_invoice_dates(candidate)
    if "MISSING_INVOICE_LINE" in remaining_codes and monthly_card:
        current_month_end = _month_end(today)
        if missing_invoice_dates and all(value > current_month_end for value in missing_invoice_dates):
            remaining_codes.remove("MISSING_INVOICE_LINE")
            false_codes.append("MISSING_INVOICE_LINE")
            evidence.append(
                "facturation mensuelle : toutes les lignes sans facture concernent des mois futurs "
                f"({missing_invoice_dates[0].isoformat()} à {missing_invoice_dates[-1].isoformat()})"
            )

    if "BOOKING_COUNT_MISMATCH" in remaining_codes:
        if len(related_series_ids) > 1 and related_dates == candidate.expected_dates:
            remaining_codes.remove("BOOKING_COUNT_MISMATCH")
            false_codes.append("BOOKING_COUNT_MISMATCH")
            evidence.append(
                f"série fragmentée en {len(related_series_ids)} identifiants mais dates agrégées complètes"
            )

    if executed_at is not None:
        late_cancelled = [
            booking
            for booking, _ in related_rows
            if booking.cancelled_at is not None
            and booking.cancelled_at.astimezone(timezone.utc) > executed_at + timedelta(seconds=30)
        ]
        session_changes = [
            session_obj
            for _, session_obj in related_rows
            if session_obj.updated_at is not None
            and session_obj.updated_at.astimezone(timezone.utc) > executed_at + timedelta(seconds=30)
        ]
        late_bookings = [
            booking
            for booking, _ in related_rows
            if booking.booked_at is not None
            and booking.booked_at.astimezone(timezone.utc) > executed_at + timedelta(seconds=30)
        ]
        if late_cancelled:
            posterior_codes.extend(code for code in remaining_codes if code == "BOOKING_COUNT_MISMATCH")
            evidence.append(f"{len(late_cancelled)} réservation(s) annulée(s) après la transformation")
        if session_changes and any(
            code in remaining_codes for code in ("BOOKING_COUNT_MISMATCH", "PLANNING_DATE_MISMATCH", "INVOICE_DATE_MISMATCH")
        ):
            posterior_codes.extend(
                code
                for code in remaining_codes
                if code in {"BOOKING_COUNT_MISMATCH", "PLANNING_DATE_MISMATCH", "INVOICE_DATE_MISMATCH"}
            )
            latest_change = max(row.updated_at for row in session_changes)
            evidence.append(
                f"planning modifié après transformation (dernière mise à jour {latest_change.isoformat()})"
            )
        if late_bookings and "BOOKING_COUNT_MISMATCH" in remaining_codes:
            posterior_codes.append("BOOKING_COUNT_MISMATCH")
            evidence.append(f"{len(late_bookings)} réservation(s) ajoutée(s) après la transformation")

        if "INVOICE_AMOUNT_MISMATCH" in remaining_codes:
            amount_changes = 0
            for booking in candidate.bookings:
                for invoice_line in candidate.invoice_lines_by_booking_id.get(booking.id, []):
                    if (
                        booking.pricing_calculated_at is not None
                        and invoice_line.created_at is not None
                        and booking.pricing_calculated_at.astimezone(timezone.utc)
                        > invoice_line.created_at.astimezone(timezone.utc) + timedelta(seconds=30)
                    ):
                        amount_changes += 1
            if amount_changes:
                posterior_codes.append("INVOICE_AMOUNT_MISMATCH")
                evidence.append(f"{amount_changes} tarif(s) de réservation recalculé(s) après facturation")

    posterior_codes = sorted(set(posterior_codes))
    unresolved_codes = [code for code in remaining_codes if code not in posterior_codes]
    if not remaining_codes:
        classification = "FALSE_ALERT"
    elif unresolved_codes:
        classification = "REAL_OR_UNEXPLAINED_GAP"
    else:
        classification = "POSTERIOR_CHANGE"

    base = candidate.public_dict()
    return {
        **base,
        "classification": classification,
        "false_alert_codes": false_codes,
        "posterior_change_codes": posterior_codes,
        "unexplained_codes": unresolved_codes,
        "execution_at": executed_at.isoformat() if executed_at is not None else None,
        "monthly_card_billing": monthly_card,
        "related_series_count": len(related_series_ids),
        "related_active_dates_count": len(related_dates),
        "missing_invoice_dates": [value.isoformat() for value in missing_invoice_dates],
        "evidence": evidence,
    }


def audit_discrepancies(*, school_year: str, today: date) -> dict[str, Any]:
    db = SessionLocal()
    try:
        checked_quotes, candidates = _audit_candidates(db, school_year=school_year)
        rows = [_classification_row(db, candidate=candidate, today=today) for candidate in candidates]
    finally:
        db.close()

    counts: dict[str, int] = {}
    for row in rows:
        label = str(row["classification"])
        counts[label] = counts.get(label, 0) + 1
    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "school_year": school_year,
        "classification_reference_date": today.isoformat(),
        "checked_quotes": checked_quotes,
        "discrepancies": len(rows),
        "classification_counts": counts,
        "items": rows,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "classification",
        "quote_number",
        "student_name",
        "activity_name",
        "location_name",
        "slot_label",
        "issue_codes",
        "false_alert_codes",
        "posterior_change_codes",
        "unexplained_codes",
        "expected_sessions",
        "booked_sessions",
        "invoiced_sessions",
        "execution_at",
        "evidence",
        "quote_id",
        "student_id",
        "series_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: " | ".join(str(item) for item in row.get(key, []))
                    if isinstance(row.get(key), list)
                    else row.get(key)
                    for key in columns
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit en lecture seule des écarts devis/planning/facturation.")
    parser.add_argument("--school-year", default="2026-2027")
    parser.add_argument("--today", type=date.fromisoformat, default=datetime.now(PARIS).date())
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    args = parser.parse_args()

    result = audit_discrepancies(school_year=args.school_year, today=args.today)
    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.json_output:
        args.json_output.write_text(payload + "\n", encoding="utf-8")
    if args.csv_output:
        _write_csv(args.csv_output, list(result["items"]))
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
