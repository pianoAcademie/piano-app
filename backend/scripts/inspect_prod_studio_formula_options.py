from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import false, func, or_, select

from app.api.routes.admin_clients import (
    INVOICE_RANGE_NOTE_PREFIX,
    _allocate_invoice_number_for_seller_entity,
    _append_private_invoice_note,
    _build_invoice_range_note_message,
    _parse_invoice_range_note_entry,
)
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
SOURCE_INVOICE_NUMBER = "PA26-0786"
REPAIR_KEY = "PROD_PIERSON_REFERRAL_CREDITS_REPAIR_20260827"
APPLY_PIERSON_REPAIR = True


def _print(line: str) -> None:
    print(f"[{SCRIPT_PREFIX}] {line}")


def _money(value: object) -> str:
    return f"{Decimal(str(value or 0)).quantize(Decimal('0.01')):.2f}"


def _object(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _uuid_texts(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _parse_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _raw_invoice_metadata(note: ClientNoteEntry) -> dict[str, object] | None:
    message = str(note.message or "")
    prefix_index = message.find(INVOICE_RANGE_NOTE_PREFIX)
    if prefix_index < 0:
        return None
    try:
        payload = json.loads(message[prefix_index + len(INVOICE_RANGE_NOTE_PREFIX) :].strip())
    except json.JSONDecodeError:
        return None
    return dict(payload) if isinstance(payload, dict) else None


def _clear_delivery_and_payment_metadata(metadata: dict[str, object]) -> None:
    for field in (
        "emailed_at",
        "reminded_at",
        "paid_at",
        "payment_url",
        "payment_provider",
        "payment_provider_reference",
        "payment_amount_paid",
        "payment_currency",
        "payment_checkout_status",
        "payment_lookup_status",
        "payment_transaction_id",
        "bank_transfer_order_id",
        "bank_transfer_order_reference",
        "bank_transfer_order_status",
        "bank_transfer_order_expires_at",
        "bank_transfer_order_paid_at",
        "reconciled_manual_payment_ids",
        "applied_payment_totals_by_currency",
        "applied_payment_lines",
        "opening_balance_by_currency",
        "credit_note_note_id",
        "credit_note_number",
    ):
        metadata.pop(field, None)


def _apply_pierson_repair(
    db,
    *,
    quote: Quote,
    followup: QuoteAcceptanceFollowup,
    payload: dict[str, object],
    execution: dict[str, object],
    notes: list[ClientNoteEntry],
) -> dict[str, object]:
    already_repaired: list[tuple[ClientNoteEntry, dict[str, object]]] = []
    for note in notes:
        metadata = _raw_invoice_metadata(note)
        if metadata is not None and metadata.get("repair_key") == REPAIR_KEY:
            already_repaired.append((note, metadata))
    if already_repaired:
        replacement = next(
            (
                metadata
                for _note, metadata in already_repaired
                if str(metadata.get("document_type") or "INVOICE").upper() == "INVOICE"
            ),
            already_repaired[0][1],
        )
        return {
            "status": "already_repaired",
            "replacement_invoice": replacement.get("invoice_number"),
            "replacement_total": replacement.get("totals_by_currency"),
        }

    source_matches: list[tuple[ClientNoteEntry, dict[str, object]]] = []
    for note in notes:
        metadata = _raw_invoice_metadata(note)
        if (
            metadata is not None
            and _parse_invoice_range_note_entry(note) is not None
            and str(metadata.get("invoice_number") or "") == SOURCE_INVOICE_NUMBER
        ):
            source_matches.append((note, metadata))
    if len(source_matches) != 1:
        raise RuntimeError(f"source_invoice_guard_failed={len(source_matches)}")
    source_note, source_metadata = source_matches[0]
    source_status = str(source_metadata.get("invoice_status") or "ISSUED").upper()
    if source_status not in {"ISSUED", "CANCELLED"}:
        raise RuntimeError(f"source_invoice_status_guard_failed={source_status}")
    if source_metadata.get("credit_note_note_id") or source_metadata.get("credit_note_number"):
        raise RuntimeError("source_invoice_already_has_credit_note")

    source_lines = list(
        db.scalars(
            select(ClientInvoiceLine)
            .where(ClientInvoiceLine.note_id == source_note.id)
            .order_by(ClientInvoiceLine.occurred_at, ClientInvoiceLine.id)
            .with_for_update()
        ).all()
    )
    source_total = sum((Decimal(line.total_incl_vat or 0) for line in source_lines), Decimal("0"))
    if source_total.quantize(Decimal("0.01")) != Decimal("1396.00"):
        raise RuntimeError(f"source_total_guard_failed={source_total}")
    positive_rates = {
        Decimal(line.vat_rate or 0).quantize(Decimal("0.001"))
        for line in source_lines
        if Decimal(line.total_incl_vat or 0) > 0
    }
    if positive_rates != {Decimal("20.000")}:
        raise RuntimeError(f"source_vat_guard_failed={sorted(positive_rates)}")
    seller_ids = {line.seller_legal_entity_id for line in source_lines}
    billing_entities = {line.billing_entity for line in source_lines}
    if len(seller_ids) != 1 or len(billing_entities) != 1:
        raise RuntimeError("source_entity_guard_failed")
    seller_id = next(iter(seller_ids))
    billing_entity = next(iter(billing_entities))

    locked_referral_rows = db.execute(
        select(ReferralReward, ClientManualTransaction)
        .join(ClientManualTransaction, ClientManualTransaction.id == ReferralReward.credit_transaction_id)
        .where(ClientManualTransaction.user_id == source_note.user_id)
        .order_by(ClientManualTransaction.occurred_at, ClientManualTransaction.id)
        .with_for_update()
    ).all()
    credits: list[ClientManualTransaction] = []
    for reward, transaction in locked_referral_rows:
        if (
            reward.status == "CREDIT_GRANTED"
            and transaction.status == "COMPLETED"
            and transaction.transaction_type == "DISCOUNT"
            and str(transaction.category or "").strip().casefold() == "parrainage"
            and str(transaction.currency or "EUR").upper() == "EUR"
            and Decimal(transaction.total_incl_vat or 0) == Decimal("-50.00")
        ):
            active_allocations = []
            allocation_notes = db.scalars(
                select(ClientNoteEntry)
                .join(ClientInvoiceLine, ClientInvoiceLine.note_id == ClientNoteEntry.id)
                .where(
                    ClientInvoiceLine.source == "MANUAL",
                    ClientInvoiceLine.source_payment_id == transaction.id,
                )
            ).all()
            for allocation_note in allocation_notes:
                allocation_metadata = _parse_invoice_range_note_entry(allocation_note)
                if allocation_metadata is None or str(
                    allocation_metadata.get("invoice_status") or "ISSUED"
                ).upper() != "CANCELLED":
                    active_allocations.append(allocation_note.id)
            if not active_allocations:
                credits.append(transaction)
    credits.sort(key=lambda row: (row.occurred_at, row.created_at, row.id))
    if len(credits) != 2:
        raise RuntimeError(f"referral_credit_guard_failed={len(credits)}")

    actor_id = _parse_uuid(execution.get("executed_by"))
    now = datetime.now(timezone.utc)
    issued_date = now.astimezone(ZoneInfo("Europe/Paris")).date()
    issued_at = datetime.combine(issued_date, datetime.min.time(), tzinfo=timezone.utc)

    credit_note_number = _allocate_invoice_number_for_seller_entity(
        db,
        seller_legal_entity_id=seller_id,
        issued_at=issued_at,
    )
    credit_metadata = dict(source_metadata)
    _clear_delivery_and_payment_metadata(credit_metadata)
    credit_reason = (
        "Annulation de la facture envoyee afin d integrer deux avoirs de parrainage de 50 EUR TTC."
    )
    credit_metadata.update(
        {
            "document_type": "CREDIT_NOTE",
            "invoice_number": credit_note_number,
            "invoice_status": "CREDIT_NOTE",
            "issued_date": issued_date.isoformat(),
            "due_date": issued_date.isoformat(),
            "no_due_date": True,
            "included_payment_keys": [],
            "totals_by_currency": {"EUR": "-1396.00"},
            "total_to_pay_by_currency": {"EUR": "0.00"},
            "original_invoice_note_id": str(source_note.id),
            "original_invoice_number": SOURCE_INVOICE_NUMBER,
            "credit_note_reason": credit_reason,
            "credited_at": issued_at.isoformat(),
            "public_note": f"Avoir relatif a la facture {SOURCE_INVOICE_NUMBER}. Motif : {credit_reason}",
            "private_note": _append_private_invoice_note(
                credit_metadata.get("private_note"),
                f"Avoir cree pour annuler {SOURCE_INVOICE_NUMBER} avant remplacement avec les avoirs de parrainage. Cle: {REPAIR_KEY}.",
            ),
            "repair_key": REPAIR_KEY,
            "repair_role": "FULL_CREDIT_NOTE",
        }
    )
    credit_note = ClientNoteEntry(
        user_id=source_note.user_id,
        author_user_id=actor_id,
        entry_type="MANUAL",
        message=_build_invoice_range_note_message(credit_metadata),
    )
    db.add(credit_note)
    db.flush()
    db.add_all(
        [
            ClientInvoiceLine(
                note_id=credit_note.id,
                user_id=source_note.user_id,
                source=line.source,
                source_payment_id=line.source_payment_id,
                occurred_at=line.occurred_at,
                label=line.label,
                amount_excl_vat=-Decimal(line.amount_excl_vat),
                vat_rate=line.vat_rate,
                vat_amount=-Decimal(line.vat_amount),
                total_incl_vat=-Decimal(line.total_incl_vat),
                currency=line.currency,
                billing_entity=line.billing_entity,
                seller_legal_entity_id=line.seller_legal_entity_id,
            )
            for line in source_lines
        ]
    )

    replacement_number = _allocate_invoice_number_for_seller_entity(
        db,
        seller_legal_entity_id=seller_id,
        issued_at=issued_at,
    )
    replacement_metadata = dict(source_metadata)
    _clear_delivery_and_payment_metadata(replacement_metadata)
    source_keys = [str(value) for value in replacement_metadata.get("included_payment_keys") or []]
    credit_keys = [f"MANUAL:{credit.id}" for credit in credits]
    replacement_metadata.update(
        {
            "document_type": "INVOICE",
            "invoice_number": replacement_number,
            "invoice_status": "ISSUED",
            "issued_date": issued_date.isoformat(),
            "due_date": source_metadata.get("due_date") or issued_date.isoformat(),
            "no_due_date": False,
            "included_payment_keys": list(dict.fromkeys([*source_keys, *credit_keys])),
            "totals_by_currency": {"EUR": "1296.00"},
            "total_to_pay_by_currency": {"EUR": "1296.00"},
            "source_quote_id": str(quote.id),
            "source_quote_number": quote.quote_number,
            "replaces_invoice_note_id": str(source_note.id),
            "replaces_invoice_number": SOURCE_INVOICE_NUMBER,
            "referral_credit_transaction_ids": [str(credit.id) for credit in credits],
            "referral_credit_total_ttc": "100.00",
            "private_note": _append_private_invoice_note(
                replacement_metadata.get("private_note"),
                f"Remplace {SOURCE_INVOICE_NUMBER}; deux avoirs de parrainage de 50 EUR TTC imputes. Cle: {REPAIR_KEY}.",
            ),
            "repair_key": REPAIR_KEY,
            "repair_role": "REPLACEMENT_INVOICE",
        }
    )
    replacement_note = ClientNoteEntry(
        user_id=source_note.user_id,
        author_user_id=actor_id,
        entry_type="MANUAL",
        message=_build_invoice_range_note_message(replacement_metadata),
    )
    db.add(replacement_note)
    db.flush()
    db.add_all(
        [
            ClientInvoiceLine(
                note_id=replacement_note.id,
                user_id=source_note.user_id,
                source=line.source,
                source_payment_id=line.source_payment_id,
                occurred_at=line.occurred_at,
                label=line.label,
                amount_excl_vat=line.amount_excl_vat,
                vat_rate=line.vat_rate,
                vat_amount=line.vat_amount,
                total_incl_vat=line.total_incl_vat,
                currency=line.currency,
                billing_entity=line.billing_entity,
                seller_legal_entity_id=line.seller_legal_entity_id,
            )
            for line in source_lines
        ]
        + [
            ClientInvoiceLine(
                note_id=replacement_note.id,
                user_id=source_note.user_id,
                source="MANUAL",
                source_payment_id=credit.id,
                occurred_at=credit.occurred_at,
                label=credit.label,
                amount_excl_vat=Decimal("-41.67"),
                vat_rate=Decimal("20.000"),
                vat_amount=Decimal("-8.33"),
                total_incl_vat=Decimal("-50.00"),
                currency="EUR",
                billing_entity=billing_entity,
                seller_legal_entity_id=seller_id,
            )
            for credit in credits
        ]
    )

    source_metadata.update(
        {
            "invoice_status": "CANCELLED",
            "credit_note_note_id": str(credit_note.id),
            "credit_note_number": credit_note_number,
            "credited_at": issued_at.isoformat(),
            "replacement_invoice_note_id": str(replacement_note.id),
            "replacement_invoice_number": replacement_number,
            "private_note": _append_private_invoice_note(
                source_metadata.get("private_note"),
                f"Facture annulee par {credit_note_number} et remplacee par {replacement_number} avec 100 EUR TTC d avoirs de parrainage.",
            ),
        }
    )
    source_note.message = _build_invoice_range_note_message(source_metadata)
    db.add(source_note)

    execution["created_annual_invoice_note_ids"] = [str(replacement_note.id)]
    execution["created_invoice_note_ids"] = list(
        dict.fromkeys(
            [
                *_uuid_texts(execution.get("created_invoice_note_ids")),
                str(credit_note.id),
                str(replacement_note.id),
            ]
        )
    )
    payload["quote_to_enrollment_execution"] = execution
    followup.payload = payload
    db.add(followup)
    db.commit()

    return {
        "status": "applied",
        "source_invoice": SOURCE_INVOICE_NUMBER,
        "source_status": "CANCELLED",
        "credit_note": credit_note_number,
        "credit_note_total": "-1396.00",
        "replacement_invoice": replacement_number,
        "replacement_total": "1296.00",
        "referral_credit_ids": [str(credit.id) for credit in credits],
    }


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
        if followup is None:
            raise RuntimeError(f"quote_followup_not_found={QUOTE_NUMBER}")
        payload = _object(followup.payload)
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
        repair_result = None
        if APPLY_PIERSON_REPAIR:
            repair_result = _apply_pierson_repair(
                db,
                quote=quote,
                followup=followup,
                payload=payload,
                execution=execution,
                notes=notes,
            )
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
            "repair_result": repair_result,
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
