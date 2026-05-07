from __future__ import annotations

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from repair_prod_gustave_guisnel_solfege1_bookings import main as _run_guisnel_solfege_repair
# Temporary runner touch for Guisnel Solfege repair.

if __name__ == "__main__":
    _run_guisnel_solfege_repair()
    raise SystemExit(0)


import argparse
import os
import secrets
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, or_, select

from app.db.session import SessionLocal
from app.models.catalog import Booking
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, ClientNoteEntry
from app.models.family import ClientFamilyLink
from app.models.plan import ClientPlanSubscription
from app.models.quote import Prospect, Quote, QuoteAcceptanceFollowup, QuoteEvent
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.services.client_status import client_status_keeps_portal_enabled, refresh_responsable_status
from app.services.security import hash_password

SCRIPT_PREFIX = "PROD_REPAIR_GERMAIN_RESPONSIBLE"
DEFAULT_QUOTE_NUMBER = "DV-20260428145937-E646"
EXECUTION_KEY = "quote_to_enrollment_execution"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_object(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: object | None) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _parse_uuid(value: object | None) -> UUID | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _normalized_email(value: object | None) -> str | None:
    raw = str(value or "").strip().lower()
    return raw or None


def _clean(value: object | None) -> str | None:
    raw = str(value or "").strip()
    return raw or None


def _safe_name(user: User | None) -> str:
    if user is None:
        return "-"
    name = " ".join(part for part in [user.first_name or "", user.last_name or ""] if part).strip()
    return name or user.email


def _user_line(user: User | None) -> str:
    if user is None:
        return "-"
    return (
        f"{user.id}|email={user.email}|name={_safe_name(user)}|"
        f"kind={user.client_kind.value}|status={user.client_status.value}|active={user.is_active}"
    )


def _quote_normalized_payload(quote: Quote) -> dict[str, object]:
    meta = _json_object(quote.meta)
    typeform_meta = _json_object(meta.get("typeform_intake"))
    return _json_object(typeform_meta.get("normalized_payload"))


def _execution_payload(followup: QuoteAcceptanceFollowup) -> dict[str, object]:
    payload = _json_object(followup.payload)
    return _json_object(payload.get(EXECUTION_KEY))


def _set_execution_payload(followup: QuoteAcceptanceFollowup, execution: dict[str, object]) -> None:
    payload = _json_object(followup.payload)
    payload[EXECUTION_KEY] = execution
    followup.payload = payload
    followup.updated_at = _utcnow()


def _parent_fields(quote: Quote, quote_prospect: Prospect | None) -> dict[str, str | None]:
    normalized = _quote_normalized_payload(quote)
    fields = {
        "first_name": _clean(normalized.get("parent_first_name")),
        "last_name": _clean(normalized.get("parent_last_name")),
        "email": _normalized_email(normalized.get("parent_email")),
        "phone": _clean(normalized.get("parent_phone")),
        "address_line": _clean(normalized.get("parent_address_line_1") or normalized.get("parent_address")),
        "postal_code": _clean(normalized.get("parent_postal_code")),
        "city": _clean(normalized.get("parent_city")),
        "country": _clean(normalized.get("parent_country")) or "FR",
    }
    line_2 = _clean(normalized.get("parent_address_line_2"))
    if line_2:
        fields["address_line"] = " - ".join(part for part in [fields["address_line"], line_2] if part)
    if any(fields[key] for key in ("first_name", "last_name", "email", "phone")):
        return fields

    meta = _json_object(quote_prospect.meta) if quote_prospect is not None else {}
    parent_referent = _json_object(meta.get("parent_referent"))
    return {
        "first_name": _clean(parent_referent.get("first_name")),
        "last_name": _clean(parent_referent.get("last_name")),
        "email": _normalized_email(parent_referent.get("email")),
        "phone": _clean(parent_referent.get("phone")),
        "address_line": _clean(parent_referent.get("address")),
        "postal_code": _clean(parent_referent.get("postal_code")),
        "city": _clean(parent_referent.get("city")),
        "country": _clean(parent_referent.get("country_code") or parent_referent.get("country")) or "FR",
    }


def _synthetic_email(quote: Quote) -> str:
    return f"parent+{quote.quote_number.lower()}@piano-academie.invalid".replace(" ", "")


def _find_or_create_parent(db, quote: Quote, fields: dict[str, str | None], *, apply: bool) -> tuple[User, bool]:
    parent_email = _normalized_email(fields.get("email"))
    parent = None
    if parent_email:
        parent = db.scalar(
            select(User)
            .where(
                func.lower(User.email) == parent_email,
                User.role == UserRole.CLIENT,
                User.client_kind == ClientKind.ADULT,
            )
            .with_for_update()
            .limit(1)
        )
    if parent is None:
        parent = User(
            email=parent_email or _synthetic_email(quote),
            hashed_password=hash_password(secrets.token_urlsafe(24)),
            role=UserRole.CLIENT,
            first_name=fields.get("first_name"),
            last_name=fields.get("last_name"),
            phone=fields.get("phone"),
            mobile_phone_1=fields.get("phone"),
            address_line=fields.get("address_line"),
            postal_code=fields.get("postal_code"),
            city=fields.get("city"),
            address_country=fields.get("country") or "FR",
            client_kind=ClientKind.ADULT,
            client_status=ClientStatus.RESPONSABLE,
            is_active=client_status_keeps_portal_enabled(ClientStatus.RESPONSABLE),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        if apply:
            db.add(parent)
            db.flush()
        return parent, True

    changed = False
    for attr, key in [
        ("first_name", "first_name"),
        ("last_name", "last_name"),
        ("phone", "phone"),
        ("mobile_phone_1", "phone"),
        ("address_line", "address_line"),
        ("postal_code", "postal_code"),
        ("city", "city"),
        ("address_country", "country"),
    ]:
        value = fields.get(key)
        if value and not str(getattr(parent, attr) or "").strip():
            setattr(parent, attr, value)
            changed = True
    if parent.client_kind != ClientKind.ADULT:
        parent.client_kind = ClientKind.ADULT
        changed = True
    if parent.client_status != ClientStatus.RESPONSABLE:
        parent.client_status = ClientStatus.RESPONSABLE
        changed = True
    desired_active = client_status_keeps_portal_enabled(parent.client_status)
    if parent.is_active != desired_active:
        parent.is_active = desired_active
        changed = True
    if changed:
        parent.updated_at = _utcnow()
        if apply:
            db.add(parent)
    return parent, False


def _load_user(db, user_id: UUID | None) -> User | None:
    if user_id is None:
        return None
    return db.scalar(select(User).where(User.id == user_id).with_for_update().limit(1))


def _ensure_billing_link(db, *, parent: User, child: User, apply: bool) -> None:
    existing_links = db.scalars(
        select(ClientFamilyLink)
        .where(ClientFamilyLink.child_user_id == child.id)
        .with_for_update()
    ).all()
    target_link = None
    for link in existing_links:
        if link.adult_user_id == parent.id:
            target_link = link
        if link.is_billing_recipient and link.adult_user_id != parent.id:
            print(f"[{SCRIPT_PREFIX}] demote_billing_link={link.id}|adult={link.adult_user_id}")
            if apply:
                link.is_billing_recipient = False
                link.updated_at = _utcnow()
                db.add(link)

    if target_link is None:
        target_link = ClientFamilyLink(
            adult_user_id=parent.id,
            child_user_id=child.id,
            relationship_label="Parent",
            is_billing_recipient=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        print(f"[{SCRIPT_PREFIX}] create_family_link=parent:{parent.id}->child:{child.id}")
        if apply:
            db.add(target_link)
            db.flush()
    elif not target_link.is_billing_recipient:
        print(f"[{SCRIPT_PREFIX}] promote_family_link_billing={target_link.id}")
        if apply:
            target_link.is_billing_recipient = True
            target_link.updated_at = _utcnow()
            db.add(target_link)


def _update_billing_references(
    db,
    *,
    quote: Quote,
    followup: QuoteAcceptanceFollowup,
    student: User,
    previous_billing: User | None,
    parent: User,
    apply: bool,
) -> dict[str, int]:
    execution = _execution_payload(followup)
    counts = {
        "subscriptions": 0,
        "transactions": 0,
        "invoice_notes": 0,
        "invoice_lines": 0,
        "execution": 0,
        "quote_meta": 0,
        "events": 0,
    }

    subscription_ids = [
        parsed for parsed in (_parse_uuid(item) for item in _json_list(execution.get("created_subscription_ids"))) if parsed
    ]
    direct_subscription_id = _parse_uuid(execution.get("subscription_id"))
    if direct_subscription_id is not None and direct_subscription_id not in subscription_ids:
        subscription_ids.append(direct_subscription_id)
    for subscription_id in subscription_ids:
        subscription = db.scalar(
            select(ClientPlanSubscription).where(ClientPlanSubscription.id == subscription_id).with_for_update().limit(1)
        )
        if subscription is not None and subscription.user_id == student.id and subscription.payer_contact_id != parent.id:
            counts["subscriptions"] += 1
            print(f"[{SCRIPT_PREFIX}] update_subscription_payer={subscription.id}")
            if apply:
                subscription.payer_contact_id = parent.id
                subscription.updated_at = _utcnow()
                db.add(subscription)

    transaction_ids = [
        parsed for parsed in (_parse_uuid(item) for item in _json_list(execution.get("created_transaction_ids"))) if parsed
    ]
    for transaction_id in transaction_ids:
        transaction = db.scalar(
            select(ClientManualTransaction)
            .where(ClientManualTransaction.id == transaction_id)
            .with_for_update()
            .limit(1)
        )
        if transaction is not None and transaction.student_user_id == student.id and transaction.user_id != parent.id:
            counts["transactions"] += 1
            print(f"[{SCRIPT_PREFIX}] update_transaction_billing={transaction.id}")
            if apply:
                transaction.user_id = parent.id
                transaction.updated_at = _utcnow()
                db.add(transaction)

    note_ids = [
        parsed for parsed in (_parse_uuid(item) for item in _json_list(execution.get("created_invoice_note_ids"))) if parsed
    ]
    for note_id in note_ids:
        note = db.scalar(select(ClientNoteEntry).where(ClientNoteEntry.id == note_id).with_for_update().limit(1))
        if note is not None and note.user_id != parent.id:
            counts["invoice_notes"] += 1
            print(f"[{SCRIPT_PREFIX}] update_invoice_note_client={note.id}")
            if apply:
                note.user_id = parent.id
                db.add(note)
        lines = db.scalars(select(ClientInvoiceLine).where(ClientInvoiceLine.note_id == note_id).with_for_update()).all()
        for line in lines:
            if line.user_id == parent.id:
                continue
            counts["invoice_lines"] += 1
            print(f"[{SCRIPT_PREFIX}] update_invoice_line_client={line.id}")
            if apply:
                line.user_id = parent.id
                db.add(line)

    if str(execution.get("billing_client_id") or "") != str(parent.id):
        counts["execution"] += 1
        print(f"[{SCRIPT_PREFIX}] update_execution_billing_client_id={parent.id}")
        if apply:
            execution["billing_client_id"] = str(parent.id)
            _set_execution_payload(followup, execution)
            db.add(followup)

    meta = _json_object(quote.meta)
    if str(meta.get("integration_billing_client_id") or "") != str(parent.id):
        counts["quote_meta"] += 1
        print(f"[{SCRIPT_PREFIX}] update_quote_meta_billing_client_id={parent.id}")
        if apply:
            meta["integration_billing_client_id"] = str(parent.id)
            quote.meta = meta
            quote.updated_at = _utcnow()
            db.add(quote)

    previous_billing_id = previous_billing.id if previous_billing is not None else _parse_uuid(execution.get("billing_client_id"))
    if previous_billing_id is not None and previous_billing_id != parent.id:
        events = db.scalars(
            select(QuoteEvent)
            .where(
                QuoteEvent.quote_id == quote.id,
                QuoteEvent.event_type == "quote_transformation_executed",
            )
            .with_for_update()
        ).all()
        for event in events:
            payload = _json_object(event.payload)
            if str(payload.get("billing_client_id") or "") == str(parent.id):
                continue
            if payload.get("billing_client_id") and str(payload.get("billing_client_id")) != str(previous_billing_id):
                continue
            counts["events"] += 1
            print(f"[{SCRIPT_PREFIX}] update_quote_event_billing={event.id}")
            if apply:
                payload["billing_client_id"] = str(parent.id)
                event.payload = payload
                db.add(event)

    return counts


def _archive_wrong_billing_if_safe(
    db,
    *,
    wrong_billing: User | None,
    parent: User,
    student: User,
    created_user_ids: set[UUID],
    apply: bool,
) -> bool:
    if wrong_billing is None or wrong_billing.id == parent.id:
        return False
    if wrong_billing.id not in created_user_ids:
        print(f"[{SCRIPT_PREFIX}] keep_previous_billing_not_created_by_transformation={wrong_billing.id}")
        return False
    if wrong_billing.client_kind != ClientKind.ADULT:
        return False
    same_as_student = (
        (wrong_billing.first_name or "").strip().casefold() == (student.first_name or "").strip().casefold()
        and (wrong_billing.last_name or "").strip().casefold() == (student.last_name or "").strip().casefold()
    )
    if not same_as_student:
        print(f"[{SCRIPT_PREFIX}] keep_previous_billing_name_differs_from_student={wrong_billing.id}")
        return False

    family_links = db.scalars(
        select(ClientFamilyLink)
        .where(
            or_(
                ClientFamilyLink.adult_user_id == wrong_billing.id,
                ClientFamilyLink.child_user_id == wrong_billing.id,
            )
        )
        .with_for_update()
    ).all()
    blockers = [
        db.scalar(select(Booking.id).where(Booking.user_id == wrong_billing.id).limit(1)) is not None,
        db.scalar(select(ClientPlanSubscription.id).where(ClientPlanSubscription.user_id == wrong_billing.id).limit(1))
        is not None,
        db.scalar(select(ClientPlanSubscription.id).where(ClientPlanSubscription.payer_contact_id == wrong_billing.id).limit(1))
        is not None,
        db.scalar(select(ClientManualTransaction.id).where(ClientManualTransaction.user_id == wrong_billing.id).limit(1))
        is not None,
        db.scalar(select(ClientNoteEntry.id).where(ClientNoteEntry.user_id == wrong_billing.id).limit(1)) is not None,
        db.scalar(select(ClientInvoiceLine.id).where(ClientInvoiceLine.user_id == wrong_billing.id).limit(1)) is not None,
    ]
    if any(blockers):
        print(f"[{SCRIPT_PREFIX}] keep_previous_billing_remaining_dependencies={wrong_billing.id}")
        return False

    print(f"[{SCRIPT_PREFIX}] archive_wrong_billing={wrong_billing.id}")
    if family_links:
        print(f"[{SCRIPT_PREFIX}] delete_wrong_billing_family_links={len(family_links)}")
    if apply:
        for link in family_links:
            db.delete(link)
        wrong_billing.client_status = ClientStatus.ARCHIVED
        wrong_billing.is_active = False
        wrong_billing.updated_at = _utcnow()
        db.add(wrong_billing)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Targeted production repair for Maxime Germain's quote responsible.")
    parser.add_argument("--quote-number", default=DEFAULT_QUOTE_NUMBER)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    mode = "apply" if args.apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    print(f"[{SCRIPT_PREFIX}] quote_number={args.quote_number}")

    with SessionLocal() as db:
        quote = db.scalar(
            select(Quote).where(Quote.quote_number == args.quote_number).with_for_update().limit(1)
        )
        if quote is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] quote_not_found")

        followup = db.scalar(
            select(QuoteAcceptanceFollowup)
            .where(QuoteAcceptanceFollowup.quote_id == quote.id)
            .with_for_update()
            .limit(1)
        )
        if followup is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] followup_not_found quote_id={quote.id}")

        execution = _execution_payload(followup)
        if str(execution.get("status") or "").strip().lower() != "executed":
            raise SystemExit(f"[{SCRIPT_PREFIX}] transformation_not_executed status={execution.get('status')}")

        student = _load_user(db, _parse_uuid(execution.get("student_client_id")) or quote.client_id or followup.target_client_id)
        if student is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] student_not_found")
        if student.client_kind != ClientKind.CHILD:
            raise SystemExit(f"[{SCRIPT_PREFIX}] student_is_not_child student={_user_line(student)}")

        previous_billing = _load_user(db, _parse_uuid(execution.get("billing_client_id")))
        quote_prospect = (
            db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id).with_for_update().limit(1))
            if quote.prospect_id is not None
            else None
        )
        parent = None
        fields = _parent_fields(quote, quote_prospect)
        if not any(fields[key] for key in ("first_name", "last_name", "email", "phone")):
            raise SystemExit(f"[{SCRIPT_PREFIX}] parent_fields_missing")
        if (
            previous_billing is not None
            and previous_billing.client_kind == ClientKind.ADULT
            and _normalized_email(previous_billing.email) == _normalized_email(fields.get("email"))
        ):
            parent = previous_billing
            created_parent = False
        else:
            parent, created_parent = _find_or_create_parent(db, quote, fields, apply=args.apply)

        print(f"[{SCRIPT_PREFIX}] student={_user_line(student)}")
        print(f"[{SCRIPT_PREFIX}] previous_billing={_user_line(previous_billing)}")
        print(
            f"[{SCRIPT_PREFIX}] target_parent={_user_line(parent)}|created={created_parent}|"
            f"parent_email={fields.get('email') or '-'}"
        )

        _ensure_billing_link(db, parent=parent, child=student, apply=args.apply)
        if args.apply:
            refresh_responsable_status(db, parent)
            db.add(parent)

        counts = _update_billing_references(
            db,
            quote=quote,
            followup=followup,
            student=student,
            previous_billing=previous_billing,
            parent=parent,
            apply=args.apply,
        )

        if args.apply:
            links = db.scalars(
                select(ClientFamilyLink)
                .where(
                    ClientFamilyLink.child_user_id == student.id,
                    ClientFamilyLink.adult_user_id != parent.id,
                )
                .with_for_update()
            ).all()
            for link in links:
                if link.is_billing_recipient:
                    link.is_billing_recipient = False
                    link.updated_at = _utcnow()
                    db.add(link)
            refresh_responsable_status(db, parent)
            if previous_billing is not None and previous_billing.id != parent.id:
                refresh_responsable_status(db, previous_billing)

        created_user_ids = {
            parsed for parsed in (_parse_uuid(item) for item in _json_list(execution.get("created_user_ids"))) if parsed
        }
        archived_wrong_billing = _archive_wrong_billing_if_safe(
            db,
            wrong_billing=previous_billing,
            parent=parent,
            student=student,
            created_user_ids=created_user_ids,
            apply=args.apply,
        )

        print(f"[{SCRIPT_PREFIX}] updated_counts={counts}")
        print(f"[{SCRIPT_PREFIX}] archived_wrong_billing={archived_wrong_billing}")

        if not args.apply:
            db.rollback()
            return

        db.commit()
        print(f"[{SCRIPT_PREFIX}] repair_complete=true")


if __name__ == "__main__":
    main()
