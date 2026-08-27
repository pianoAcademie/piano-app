from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import false, func, or_, select

from app.api.routes.admin_clients import _parse_invoice_range_note_entry
from app.api.routes.clients import _active_formula_options_for_course_type, _session_purchase_catalog
from app.db.session import SessionLocal
from app.models.catalog import CourseSession, CourseType, CreditType, Location
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, ClientNoteEntry
from app.models.plan import Plan, PlanCreditGrant, PlanEntitlement, PlanKind
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteLine
from app.models.referral import ReferralReward
from app.services.session_audience import resolve_session_booking_scopes

SCRIPT_PREFIX = "PROD_PIERSON_INVOICE_AUDIT_20260827"
QUOTE_NUMBER = "DV-20260824133038-3F67"


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _money(value: object) -> str:
    return f"{Decimal(str(value or 0)).quantize(Decimal('0.01')):.2f}"


def _object(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _uuid_texts(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def main() -> None:
    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER))
        if quote is None:
            raise RuntimeError(f"quote_not_found={QUOTE_NUMBER}")
        followup = db.scalar(
            select(QuoteAcceptanceFollowup)
            .where(QuoteAcceptanceFollowup.quote_id == quote.id)
            .order_by(QuoteAcceptanceFollowup.created_at.desc())
            .limit(1)
        )
        payload = _object(followup.payload if followup is not None else {})
        execution = _object(payload.get("quote_to_enrollment_execution"))
        billing_id = execution.get("billing_client_id")
        if not billing_id:
            raise RuntimeError("billing_client_id_missing")

        quote_lines = list(
            db.scalars(
                select(QuoteLine)
                .where(QuoteLine.quote_id == quote.id)
                .order_by(QuoteLine.sort_order, QuoteLine.created_at, QuoteLine.id)
            ).all()
        )
        notes = list(
            db.scalars(
                select(ClientNoteEntry)
                .where(ClientNoteEntry.user_id == billing_id)
                .order_by(ClientNoteEntry.created_at, ClientNoteEntry.id)
            ).all()
        )
        invoice_rows: list[dict[str, object]] = []
        for note in notes:
            metadata = _parse_invoice_range_note_entry(note)
            if metadata is None:
                continue
            number = str(metadata.get("invoice_number") or "")
            if not number.startswith("PA26-07") and str(metadata.get("source_quote_number") or "") != QUOTE_NUMBER:
                continue
            lines = list(
                db.scalars(
                    select(ClientInvoiceLine)
                    .where(ClientInvoiceLine.note_id == note.id)
                    .order_by(ClientInvoiceLine.occurred_at, ClientInvoiceLine.id)
                ).all()
            )
            invoice_rows.append(
                {
                    "note_id": str(note.id),
                    "created_at": note.created_at.isoformat(),
                    "number": number,
                    "status": metadata.get("invoice_status"),
                    "document_type": metadata.get("document_type"),
                    "emailed_at": metadata.get("emailed_at"),
                    "source_quote_number": metadata.get("source_quote_number"),
                    "original_invoice_number": metadata.get("original_invoice_number"),
                    "credit_note_number": metadata.get("credit_note_number"),
                    "totals": metadata.get("totals_by_currency"),
                    "due": metadata.get("total_to_pay_by_currency"),
                    "included_payment_keys": metadata.get("included_payment_keys"),
                    "referral_credit_ids": metadata.get("referral_credit_transaction_ids"),
                    "line_total": _money(sum((Decimal(line.total_incl_vat or 0) for line in lines), Decimal("0"))),
                    "lines": [
                        {
                            "source": line.source,
                            "source_payment_id": str(line.source_payment_id),
                            "label": line.label,
                            "occurred_at": line.occurred_at.isoformat(),
                            "ht": _money(line.amount_excl_vat),
                            "vat_rate": str(line.vat_rate),
                            "vat": _money(line.vat_amount),
                            "ttc": _money(line.total_incl_vat),
                            "seller": str(line.seller_legal_entity_id or ""),
                        }
                        for line in lines
                    ],
                }
            )

        referral_rows = db.execute(
            select(ReferralReward, ClientManualTransaction)
            .join(ClientManualTransaction, ClientManualTransaction.id == ReferralReward.credit_transaction_id)
            .where(ClientManualTransaction.user_id == billing_id)
            .order_by(ClientManualTransaction.occurred_at, ClientManualTransaction.id)
        ).all()
        referral_credits = []
        for reward, transaction in referral_rows:
            allocations = list(
                db.execute(
                    select(ClientInvoiceLine.note_id, ClientNoteEntry.message)
                    .join(ClientNoteEntry, ClientNoteEntry.id == ClientInvoiceLine.note_id)
                    .where(
                        ClientInvoiceLine.source == "MANUAL",
                        ClientInvoiceLine.source_payment_id == transaction.id,
                    )
                ).all()
            )
            referral_credits.append(
                {
                    "reward_id": str(reward.id),
                    "reward_status": reward.status,
                    "transaction_id": str(transaction.id),
                    "transaction_status": transaction.status,
                    "label": transaction.label,
                    "category": transaction.category,
                    "ttc": _money(transaction.total_incl_vat),
                    "allocations": [
                        {
                            "note_id": str(note_id),
                            "invoice": (_parse_invoice_range_note_entry(ClientNoteEntry(message=message)) or {}).get(
                                "invoice_number"
                            ),
                            "status": (_parse_invoice_range_note_entry(ClientNoteEntry(message=message)) or {}).get(
                                "invoice_status"
                            ),
                        }
                        for note_id, message in allocations
                    ],
                }
            )

        result = {
            "quote": {
                "id": str(quote.id),
                "number": quote.quote_number,
                "status": quote.status,
                "total_ht": _money(sum((Decimal(line.amount_ht or 0) for line in quote_lines), Decimal("0"))),
                "total_vat": _money(sum((Decimal(line.amount_vat or 0) for line in quote_lines), Decimal("0"))),
                "total_ttc": _money(quote.total_ttc),
                "lines": [
                    {
                        "id": str(line.id),
                        "title": line.title,
                        "category": line.line_category,
                        "quantity": str(line.quantity),
                        "ht": _money(line.amount_ht),
                        "vat_rate": str(line.vat_rate),
                        "vat": _money(line.amount_vat),
                        "ttc": _money(line.amount_ttc),
                    }
                    for line in quote_lines
                ],
            },
            "execution": {
                "billing_client_id": str(billing_id),
                "student_client_id": execution.get("student_client_id"),
                "created_booking_ids": len(_uuid_texts(execution.get("created_booking_ids"))),
                "created_transaction_ids": _uuid_texts(execution.get("created_transaction_ids")),
                "created_annual_invoice_note_ids": _uuid_texts(
                    execution.get("created_annual_invoice_note_ids")
                ),
                "created_invoice_note_ids": _uuid_texts(execution.get("created_invoice_note_ids")),
            },
            "invoices": invoice_rows,
            "referral_credits": referral_credits,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

        studio_course_types = db.execute(
            select(
                CourseType.id,
                CourseType.name,
                CourseType.service_code,
                CourseType.mode,
                CourseType.credit_type_id,
                CreditType.code,
                CreditType.name,
            )
            .join(CreditType, CreditType.id == CourseType.credit_type_id, isouter=True)
            .where(func.lower(CourseType.name).like("%studio%"))
            .order_by(CourseType.name.asc())
        ).all()

        if not studio_course_types:
            _print("no studio course types found")
            return

        _print(f"studio_course_types={len(studio_course_types)}")
        for row in studio_course_types:
            course_type_id, name, service_code, course_type_mode, credit_type_id, credit_code, credit_name = row
            _print(
                "course_type="
                f"{course_type_id}|name={name}|service_code={service_code or '-'}|"
                f"credit_type_id={credit_type_id or '-'}|credit_type_code={credit_code or '-'}|credit_type_name={credit_name or '-'}"
            )

            exact_public_plans = db.execute(
                select(
                    Plan.id,
                    Plan.code,
                    Plan.name,
                    Plan.kind,
                    Plan.active,
                    Plan.is_private,
                )
                .select_from(Plan)
                .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id)
                .where(
                    PlanEntitlement.course_type_id == course_type_id,
                    Plan.active.is_(True),
                    Plan.is_private.is_(False),
                )
                .order_by(Plan.name.asc())
            ).all()
            _print(f"exact_public_plans_for_{name}={len(exact_public_plans)}")
            for plan_id, plan_code, plan_name, kind, active, is_private in exact_public_plans:
                _print(
                    "exact_public_plan="
                    f"{plan_id}|code={plan_code}|name={plan_name}|kind={getattr(kind, 'value', kind)}|"
                    f"active={active}|private={is_private}"
                )

            entitlement_rows = db.execute(
                select(
                    Plan.id,
                    Plan.code,
                    Plan.name,
                    Plan.kind,
                    Plan.active,
                    Plan.is_private,
                    Plan.options_json,
                    PlanEntitlement.course_type_id,
                    PlanCreditGrant.credit_type_id,
                    PlanCreditGrant.credits_count,
                )
                .select_from(Plan)
                .join(PlanEntitlement, PlanEntitlement.plan_id == Plan.id, isouter=True)
                .join(PlanCreditGrant, PlanCreditGrant.plan_id == Plan.id, isouter=True)
                .where(
                    or_(
                        PlanEntitlement.course_type_id == course_type_id,
                        PlanCreditGrant.credit_type_id == credit_type_id if credit_type_id is not None else false(),
                        func.lower(Plan.name).like("%studio%"),
                        func.lower(Plan.code).like("%studio%"),
                    )
                )
                .order_by(Plan.name.asc())
            ).all()
            _print(f"matching_plan_rows_for_{name}={len(entitlement_rows)}")
            for prow in entitlement_rows:
                (
                    plan_id,
                    plan_code,
                    plan_name,
                    kind,
                    active,
                    is_private,
                    options_json,
                    entitlement_course_type_id,
                    grant_credit_type_id,
                    grant_credits_count,
                ) = prow
                _print(
                    "plan_row="
                    f"{plan_id}|code={plan_code}|name={plan_name}|kind={getattr(kind, 'value', kind)}|"
                    f"active={active}|private={is_private}|options={options_json}|"
                    f"entitlement_course_type_id={entitlement_course_type_id or '-'}|"
                    f"grant_credit_type_id={grant_credit_type_id or '-'}|grant_credits_count={grant_credits_count or 0}"
                )

            formula_options = _active_formula_options_for_course_type(
                db,
                course_type_id=course_type_id,
                course_type_name=name,
                course_type_service_code=service_code,
                course_type_mode=course_type_mode,
                credit_type_id=credit_type_id,
                allowed_plan_kinds={PlanKind.PACK, PlanKind.SUBSCRIPTION, PlanKind.FORFAIT},
            )
            _print(
                f"formula_options_for_{name}="
                + (
                    ",".join(
                        f"{option.formula_code}:{option.name}:{getattr(option.formula_type, 'value', option.formula_type)}"
                        for option in formula_options
                    )
                    or "-"
                )
            )

        now = datetime.now(timezone.utc)
        upcoming_sessions = db.execute(
            select(CourseSession, CourseType, Location)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(
                func.lower(CourseType.name).like("%studio%"),
                CourseSession.start_at_utc >= now - timedelta(days=3),
                CourseSession.start_at_utc <= now + timedelta(days=30),
            )
            .order_by(CourseSession.start_at_utc.asc())
        ).all()
        _print(f"upcoming_studio_sessions={len(upcoming_sessions)}")
        for session_obj, course_type, location in upcoming_sessions:
            formula_options, direct_payment_amount, direct_payment_currency, session_booking_scopes = _session_purchase_catalog(
                db,
                session_obj=session_obj,
                course_type=course_type,
            )
            _print(
                "session="
                f"{session_obj.id}|start_at_utc={session_obj.start_at_utc.isoformat()}|location={location.name}|"
                f"course_type={course_type.name}|course_type_id={course_type.id}|"
                f"credit_type_id={course_type.credit_type_id or '-'}|status={getattr(session_obj.status, 'value', session_obj.status)}|"
                f"price={session_obj.external_booking_price_ttc or '-'} EUR|"
                f"booking_scopes={','.join(scope.value for scope in resolve_session_booking_scopes(session_obj, allows_student_bookings=bool(course_type.allows_student_bookings)))}|"
                f"catalog_scopes={','.join(scope.value for scope in session_booking_scopes)}|"
                f"catalog_direct_payment={direct_payment_amount or '-'} {direct_payment_currency or '-'}|"
                f"catalog_formulas={(','.join(option.formula_code for option in formula_options) or '-')}"
            )


if __name__ == "__main__":
    main()
