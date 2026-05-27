from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.client_record import ClientInvoiceLine, ClientManualTransaction, ClientNoteEntry
from app.models.family import ClientFamilyLink
from app.models.plan import ClientPlanSubscription
from app.models.quote import Prospect, Quote, QuoteAcceptanceFollowup, QuoteEvent
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.services.client_status import client_status_keeps_portal_enabled, refresh_responsable_status
from app.services.security import hash_password

SCRIPT_PREFIX = "PROD_REPAIR_BASILE_IMBERT_RESPONSIBLE"
EXECUTION_KEY = "quote_to_enrollment_execution"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_object(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: object | None) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _clean(value: object | None) -> str | None:
    raw = str(value or "").strip()
    return raw or None


def _norm(value: object | None) -> str:
    return str(value or "").strip().casefold()


def _normalized_email(value: object | None) -> str | None:
    raw = str(value or "").strip().lower()
    return raw or None


def _parse_uuid(value: object | None) -> UUID | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


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


def _parent_fields(
    quote: Quote,
    quote_prospect: Prospect | None,
    *,
    fallback_first_name: str,
    fallback_last_name: str,
    fallback_email: str,
) -> dict[str, str | None]:
    normalized = _quote_normalized_payload(quote)
    fields = {
        "first_name": _clean(normalized.get("parent_first_name")) or fallback_first_name,
        "last_name": _clean(normalized.get("parent_last_name")) or fallback_last_name,
        "email": _normalized_email(normalized.get("parent_email")) or _normalized_email(fallback_email),
        "phone": _clean(normalized.get("parent_phone")),
        "address_line": _clean(normalized.get("parent_address_line_1") or normalized.get("parent_address")),
        "postal_code": _clean(normalized.get("parent_postal_code")),
        "city": _clean(normalized.get("parent_city")),
        "country": _clean(normalized.get("parent_country")) or "FR",
    }
    line_2 = _clean(normalized.get("parent_address_line_2"))
    if line_2:
        fields["address_line"] = " - ".join(part for part in [fields["address_line"], line_2] if part)

    meta = _json_object(quote_prospect.meta) if quote_prospect is not None else {}
    parent_referent = _json_object(meta.get("parent_referent"))
    for key, meta_key in [
        ("first_name", "first_name"),
        ("last_name", "last_name"),
        ("email", "email"),
        ("phone", "phone"),
        ("address_line", "address"),
        ("postal_code", "postal_code"),
        ("city", "city"),
    ]:
        if not fields.get(key):
            fields[key] = _normalized_email(parent_referent.get(meta_key)) if key == "email" else _clean(parent_referent.get(meta_key))
    if not fields.get("country"):
        fields["country"] = _clean(parent_referent.get("country_code") or parent_referent.get("country")) or "FR"
    return fields


def _matches_name(user: User | None, first_name: str, last_name: str) -> bool:
    if user is None:
        return False
    return _norm(user.first_name) == _norm(first_name) and _norm(user.last_name) == _norm(last_name)


def _matches_prospect_name(prospect: Prospect | None, first_name: str, last_name: str) -> bool:
    if prospect is None:
        return False
    return _norm(prospect.first_name) == _norm(first_name) and _norm(prospect.last_name) == _norm(last_name)


def _load_user(db, user_id: UUID | None) -> User | None:
    if user_id is None:
        return None
    return db.scalar(select(User).where(User.id == user_id).with_for_update().limit(1))


def _target_parent(db, fields: dict[str, str | None], *, apply: bool) -> tuple[User, bool]:
    email = _normalized_email(fields.get("email"))
    if not email:
        raise SystemExit(f"[{SCRIPT_PREFIX}] target_parent_email_missing")
    parent = db.scalar(select(User).where(func.lower(User.email) == email).with_for_update().limit(1))
    if parent is None:
        parent = User(
            email=email,
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
        print(f"[{SCRIPT_PREFIX}] create_target_parent={email}")
        if apply:
            db.add(parent)
            db.flush()
        return parent, True

    changed = False
    if parent.role != UserRole.CLIENT:
        raise SystemExit(f"[{SCRIPT_PREFIX}] target_email_not_client user={_user_line(parent)}")
    if parent.client_kind != ClientKind.ADULT:
        print(f"[{SCRIPT_PREFIX}] fix_target_parent_kind={parent.id}")
        parent.client_kind = ClientKind.ADULT
        changed = True

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
        if not value:
            continue
        current = str(getattr(parent, attr) or "").strip()
        if attr in {"first_name", "last_name"}:
            expected = str(value).strip()
            if current != expected:
                print(f"[{SCRIPT_PREFIX}] update_target_parent_{attr}={current or '-'}->{expected}")
                setattr(parent, attr, expected)
                changed = True
        elif not current:
            setattr(parent, attr, value)
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


def _ensure_billing_link(db, *, parent: User, child: User, apply: bool) -> None:
    links = db.scalars(select(ClientFamilyLink).where(ClientFamilyLink.child_user_id == child.id).with_for_update()).all()
    target = None
    for link in links:
        if link.adult_user_id == parent.id:
            target = link
        elif link.is_billing_recipient:
            print(f"[{SCRIPT_PREFIX}] demote_previous_billing_link={link.id}|adult={link.adult_user_id}")
            if apply:
                link.is_billing_recipient = False
                link.updated_at = _utcnow()
                db.add(link)
    if target is None:
        target = ClientFamilyLink(
            adult_user_id=parent.id,
            child_user_id=child.id,
            relationship_label="Parent",
            is_billing_recipient=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        print(f"[{SCRIPT_PREFIX}] create_family_link=parent:{parent.id}->child:{child.id}")
        if apply:
            db.add(target)
            db.flush()
    elif not target.is_billing_recipient:
        print(f"[{SCRIPT_PREFIX}] promote_family_link_billing={target.id}")
        if apply:
            target.is_billing_recipient = True
            target.updated_at = _utcnow()
            db.add(target)


def _update_billing_references(
    db,
    *,
    quote: Quote,
    followup: QuoteAcceptanceFollowup,
    student: User,
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
        subscription = db.scalar(select(ClientPlanSubscription).where(ClientPlanSubscription.id == subscription_id).with_for_update().limit(1))
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
        transaction = db.scalar(select(ClientManualTransaction).where(ClientManualTransaction.id == transaction_id).with_for_update().limit(1))
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

    events = db.scalars(select(QuoteEvent).where(QuoteEvent.quote_id == quote.id, QuoteEvent.event_type == "quote_transformation_executed").with_for_update()).all()
    for event in events:
        payload = _json_object(event.payload)
        if str(payload.get("billing_client_id") or "") == str(parent.id):
            continue
        counts["events"] += 1
        print(f"[{SCRIPT_PREFIX}] update_quote_event_billing={event.id}")
        if apply:
            payload["billing_client_id"] = str(parent.id)
            event.payload = payload
            db.add(event)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Targeted production repair for Basile Imbert's responsible adult.")
    parser.add_argument("--child-first-name", default="Basile")
    parser.add_argument("--child-last-name", default="Imbert")
    parser.add_argument("--parent-first-name", default="Florence")
    parser.add_argument("--parent-last-name", default="Valiergue")
    parser.add_argument("--parent-email", default="flovaliergue@gmail.com")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    mode = "apply" if args.apply else "dry-run"
    print(f"[{SCRIPT_PREFIX}] mode={mode}")
    print(f"[{SCRIPT_PREFIX}] child={args.child_first_name} {args.child_last_name}")
    print(f"[{SCRIPT_PREFIX}] parent={args.parent_first_name} {args.parent_last_name} <{args.parent_email}>")

    processed = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(Quote, QuoteAcceptanceFollowup)
            .join(QuoteAcceptanceFollowup, QuoteAcceptanceFollowup.quote_id == Quote.id)
            .order_by(Quote.created_at.asc())
        ).all()
        for quote, followup in rows:
            execution = _execution_payload(followup)
            if str(execution.get("status") or "").strip().lower() != "executed":
                continue
            quote_prospect = (
                db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id).with_for_update().limit(1))
                if quote.prospect_id is not None
                else None
            )
            student = _load_user(
                db,
                _parse_uuid(execution.get("student_client_id")) or quote.client_id or followup.target_client_id,
            )
            if not (
                _matches_name(student, args.child_first_name, args.child_last_name)
                or _matches_prospect_name(quote_prospect, args.child_first_name, args.child_last_name)
            ):
                continue
            if student is None:
                raise SystemExit(f"[{SCRIPT_PREFIX}] matching_quote_without_student quote={quote.quote_number}")
            if student.client_kind != ClientKind.CHILD:
                raise SystemExit(f"[{SCRIPT_PREFIX}] matching_student_not_child quote={quote.quote_number}|student={_user_line(student)}")

            fields = _parent_fields(
                quote,
                quote_prospect,
                fallback_first_name=args.parent_first_name,
                fallback_last_name=args.parent_last_name,
                fallback_email=args.parent_email,
            )
            fields["first_name"] = args.parent_first_name
            fields["last_name"] = args.parent_last_name
            fields["email"] = _normalized_email(args.parent_email)

            parent, created_parent = _target_parent(db, fields, apply=args.apply)
            previous_billing = _load_user(db, _parse_uuid(execution.get("billing_client_id")))

            print(f"[{SCRIPT_PREFIX}] quote={quote.quote_number}|quote_id={quote.id}")
            print(f"[{SCRIPT_PREFIX}] student={_user_line(student)}")
            print(f"[{SCRIPT_PREFIX}] previous_billing={_user_line(previous_billing)}")
            print(f"[{SCRIPT_PREFIX}] target_parent={_user_line(parent)}|created={created_parent}")

            _ensure_billing_link(db, parent=parent, child=student, apply=args.apply)
            if quote_prospect is not None and quote_prospect.parent_prospect_id is not None:
                parent_prospect = db.scalar(
                    select(Prospect).where(Prospect.id == quote_prospect.parent_prospect_id).with_for_update().limit(1)
                )
                if parent_prospect is not None and parent_prospect.linked_client_id != parent.id:
                    print(f"[{SCRIPT_PREFIX}] update_parent_prospect_client={parent_prospect.id}")
                    if args.apply:
                        parent_prospect.linked_client_id = parent.id
                        parent_prospect.status = "converted"
                        parent_prospect.updated_at = _utcnow()
                        db.add(parent_prospect)

            counts = _update_billing_references(
                db,
                quote=quote,
                followup=followup,
                student=student,
                parent=parent,
                apply=args.apply,
            )
            print(f"[{SCRIPT_PREFIX}] updated_counts={counts}")

            if args.apply:
                refresh_responsable_status(db, parent)
                db.add(parent)
                if previous_billing is not None and previous_billing.id != parent.id:
                    refresh_responsable_status(db, previous_billing)
                    db.add(previous_billing)
            processed += 1

        print(f"[{SCRIPT_PREFIX}] processed_quotes={processed}")
        if processed == 0:
            raise SystemExit(f"[{SCRIPT_PREFIX}] no_matching_executed_quote_found")
        if args.apply:
            db.commit()
            print(f"[{SCRIPT_PREFIX}] repair_complete=true")
        else:
            db.rollback()


if __name__ == "__main__":
    main()
