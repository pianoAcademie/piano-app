"""Fixed-amount payment requests attached to an existing invoice.

All mutations lock the invoice note. Requests/attempts live in its existing JSON
metadata: no new invoice, charge line, booking or expected cash receipt is made.
Provider references belong to individual attempts, never to a mutable 'latest'
invoice reference. Only verified PSP settlements create accounting movements.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from urllib.parse import urlencode

import jwt
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import admin_clients as invoices
from app.core.config import settings
from app.models.client_record import ClientManualTransaction
from app.models.user import User
from app.services.email_branding import render_branded_email
from app.services.payment_checkout import CheckoutCreateRequest, create_checkout_session, lookup_payment, with_webhook_secret
from app.services.payment_provider import PaymentProvider, resolve_webhook_secret

FIELD = "partial_payment_requests"
SCOPE = "INVOICE_PARTIAL_PAYMENT"
ACTIVE = {"READY", "CREATING", "PENDING", "REVIEW"}


def money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " €"


def requests(metadata: dict) -> list[dict]:
    return metadata.setdefault(FIELD, [])


def active_requests(metadata: dict) -> list[dict]:
    now = invoices._utcnow()
    return [r for r in requests(metadata) if r["status"] in ACTIVE and not (
        r["status"] == "READY" and invoices._parse_optional_datetime(r["expires_at"]) <= now
    )]


def assert_no_active_partial_request(metadata: dict) -> None:
    if active_requests(metadata):
        raise HTTPException(409, "Un lien de paiement partiel est actif. Utilisez ce lien ou annulez-le avant de régler tout le solde.")


def balance(metadata: dict) -> Decimal:
    amounts = metadata.get("total_to_pay_by_currency") or metadata.get("totals_by_currency") or {}
    if set(amounts) != {"EUR"}:
        raise HTTPException(422, "Le paiement partiel est disponible pour les factures en euros uniquement.")
    value = Decimal(str(amounts["EUR"]))
    if not value.is_finite():
        raise HTTPException(422, "Solde de facture invalide.")
    return value.quantize(Decimal("0.01"))  # Never abs(): a credit is not an amount to collect.


def load(db: Session, client_id: UUID, note_id: UUID):
    # The PSP/email request can outlast the application's default 15-second idle timeout.
    db.execute(text("SET LOCAL idle_in_transaction_session_timeout = '120s'"))
    db.expire_all()
    owner = invoices._require_client(db, client_id)
    note, metadata = invoices._load_range_invoice_note(db, client_id=client_id, note_id=note_id, for_update=True)
    if owner.id != note.user_id:
        owner = invoices._require_client(db, note.user_id)
    metadata = invoices._invoice_range_metadata_with_display_totals(
        db, client_id=note.user_id, note_id=note_id, note_created_at=note.created_at, metadata=metadata,
    )
    payer = invoices._invoice_family_payer_from_metadata(db, owner_client=owner, metadata=metadata)
    return note, metadata, payer


def ensure_payable(metadata: dict) -> None:
    if metadata.get("document_type", "INVOICE") != "INVOICE" or metadata.get("invoice_status") != "ISSUED":
        raise HTTPException(409, "Seule une facture émise non soldée peut recevoir un paiement partiel.")
    if balance(metadata) <= 0:
        raise HTTPException(409, "Aucun montant à régler sur cette facture.")


def find(metadata: dict, request_id: UUID) -> dict:
    for row in requests(metadata):
        if row["id"] == str(request_id):
            return row
    raise HTTPException(404, "Demande de paiement introuvable.")


def save(db: Session, note, metadata: dict) -> None:
    note.message = invoices._build_invoice_range_note_message(metadata)
    db.add(note)
    db.commit()


def token_for(note, metadata: dict, row: dict, *, attempt_id: str | None = None) -> str:
    payload = {"scope": SCOPE, "client_id": str(note.user_id), "note_id": str(note.id),
        "invoice_number": metadata["invoice_number"], "request_id": row["id"], "attempt_id": attempt_id,
        # Checkout callbacks remain valid after the customer-facing link expires.
        "exp": int((invoices._utcnow() + timedelta(days=365)).timestamp()) if attempt_id else
            int(invoices._parse_optional_datetime(row["expires_at"]).timestamp())}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_token(token: str, note, metadata: dict, row: dict, *, attempt_id: str | None = None) -> None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(403, "Lien de paiement invalide ou expiré.") from exc
    expected = {"scope": SCOPE, "client_id": str(note.user_id), "note_id": str(note.id),
        "invoice_number": metadata["invoice_number"], "request_id": row["id"], "attempt_id": attempt_id}
    if any(payload.get(key) != value for key, value in expected.items()):
        raise HTTPException(403, "Lien de paiement invalide.")


def public_url(note, metadata: dict, row: dict) -> str:
    return (f"{invoices._frontend_base_url()}/api/v1/public/payments/partial/{note.user_id}/{note.id}/{row['id']}?"
            + urlencode({"token": token_for(note, metadata, row)}))


def recipients_for(db: Session, payer: User) -> list[str]:
    profile = invoices.resolve_billing_profile(db, payer)
    recipients = invoices._normalize_email_recipients([profile.email, payer.email])
    if not recipients:
        raise HTTPException(422, "Aucune adresse email de facturation disponible.")
    return recipients


def branded_message(note, metadata: dict, row: dict, payer: User, *, receipt: bool = False) -> tuple[str, str]:
    amount = Decimal(row["amount"])
    remaining = max(Decimal("0.00"), balance(metadata) if receipt else balance(metadata) - amount)
    number = metadata["invoice_number"]
    name = invoices._display_name(payer.first_name, payer.last_name, payer.email)
    subject = f"{'Paiement reçu' if receipt else 'Paiement partiel'} de {money(amount)} — facture {number}"
    body = render_branded_email(
        preview=subject, eyebrow="PAIEMENT", title="Paiement bien reçu" if receipt else "Régler une partie de votre facture",
        greeting=f"Bonjour {name},",
        intro=("Votre paiement par carte a bien été confirmé." if receipt else
            "Vous pouvez régler le montant ci-dessous par carte, sur votre facture existante."),
        rows=[("Facture", number), ("Montant de la facture", money(Decimal(metadata["totals_by_currency"]["EUR"]))),
            ("Montant reçu" if receipt else "Montant à régler par carte", money(amount)),
            ("Solde restant" if receipt else "Solde après ce paiement confirmé", money(remaining))],
        message=("Aucune nouvelle facture n’est créée. Les autres règlements ne seront déduits qu’une fois enregistrés comme reçus."
            if not receipt else ("La facture reste à régler pour le solde indiqué." if remaining > 0 else "La facture est soldée.")),
        button_url=None if receipt else public_url(note, metadata, row),
        button_label=None if receipt else f"Payer {money(amount)} par carte",
        links=[("Consulter la facture", invoices._invoice_range_download_url(client_id=note.user_id, note_id=note.id, metadata=metadata, inline=True))],
    )
    return subject, body


def send_message(db: Session, note, metadata: dict, row: dict, payer: User, *, receipt: bool = False) -> None:
    recipients = row["recipients"]
    subject, body = branded_message(note, metadata, row, payer, receipt=receipt)
    sender = invoices.resolve_sender_profile(db, sender_kind="STUDIO")
    marker = "receipt_sent_to" if receipt else "link_sent_to"
    sent = row.setdefault(marker, [])
    for recipient in recipients:
        if recipient in sent:
            continue
        invoices.send_email(
            to_email=recipient, subject=subject, body=body, body_format="HTML",
            context="INVOICE_PARTIAL_PAYMENT_RECEIPT" if receipt else "INVOICE_PARTIAL_PAYMENT_REQUEST",
            from_email=sender.from_email, from_name=sender.from_name, reply_to=sender.reply_to,
            subject_prefix=sender.subject_prefix, recipient_user_id=payer.id,
            sender_user_id=UUID(row["actor_id"]) if not receipt else None,
            communication_type=invoices.COMMUNICATION_TYPE_OPERATIONAL, raise_on_failure=True,
        )
        sent.append(recipient)
    row["receipt_sent_at" if receipt else "sent_at"] = invoices._utcnow().isoformat()


def check_other_checkout(db: Session, client_id: UUID, note_id: UUID, metadata: dict) -> None:
    """Do not compete with an already-issued full-invoice checkout or bank order."""
    order = invoices._latest_bank_transfer_order_for_invoice(db, client_id=client_id, note_id=note_id)
    if order and order.status == invoices.BANK_TRANSFER_ORDER_STATUS_PENDING:
        raise HTTPException(409, "Un ordre de virement est déjà en attente sur cette facture.")
    ref = metadata.get("payment_provider_reference")
    if ref and not metadata.get("payment_transaction_id"):
        provider = invoices.detect_provider_from_reference(ref) or invoices.parse_provider(metadata.get("payment_provider"))
        result = lookup_payment(db, provider=provider, payment_reference=ref)
        if not result.success or result.paid or not (result.failed or result.cancelled):
            raise HTTPException(409, "Un paiement du solde est en cours ou doit être rapproché. Vérifiez-le avant de demander un paiement partiel.")


def create_request(db: Session, *, client_id: UUID, note_id: UUID, request_id: UUID, amount: Decimal, actor: User) -> dict:
    note, metadata, payer = load(db, client_id, note_id)
    existing = next((r for r in requests(metadata) if r["id"] == str(request_id)), None)
    if existing:
        if Decimal(existing["amount"]) != amount:
            raise HTTPException(409, "Cette demande existe déjà avec un autre montant. Actualisez la facture.")
        row = existing
        if row not in active_requests(metadata):
            raise HTTPException(409, "Cette demande est terminée ou expirée. Actualisez la facture.")
    else:
        ensure_payable(metadata)
        if not amount.is_finite() or amount < 1 or amount != amount.quantize(Decimal("0.01")) or amount >= balance(metadata):
            raise HTTPException(422, "Indiquez un montant d’au moins 1 €, avec deux décimales au plus, strictement inférieur au solde restant.")
        assert_no_active_partial_request(metadata)
        check_other_checkout(db, note.user_id, note.id, metadata)
        row = {"id": str(request_id), "amount": f"{amount:.2f}", "currency": "EUR", "status": "READY",
            "actor_id": str(actor.id), "created_at": invoices._utcnow().isoformat(),
            "expires_at": (invoices._utcnow() + timedelta(days=30)).isoformat(),
            "recipients": recipients_for(db, payer), "attempts": []}
        requests(metadata).append(row)
        save(db, note, metadata)  # Persist the idempotency key before calling email delivery.
        note, metadata, payer = load(db, client_id, note_id)
        row = find(metadata, request_id)
    try:
        send_message(db, note, metadata, row, payer)
        row.pop("email_error", None)
    except Exception:
        row["email_error"] = "L’envoi du courriel n’a pas été confirmé. Réessayez avec cette même demande."
    save(db, note, metadata)
    return {"request_id": row["id"], "sent": not bool(row.get("email_error")), "error": row.get("email_error"),
        "amount": row["amount"], "remaining_after_payment": f"{balance(metadata) - amount:.2f}", "recipients": row["recipients"]}


def settle(db: Session, note, metadata: dict, row: dict, attempt: dict, lookup) -> bool:
    """Called under the invoice lock; callbacks and return URL share this path."""
    if attempt.get("transaction_id"):
        return True
    if not lookup.success:
        raise HTTPException(503, "La vérification bancaire est momentanément indisponible.")
    attempt["lookup_status"] = lookup.status
    if not lookup.paid:
        attempt["status"] = "FAILED" if lookup.failed or lookup.cancelled else "PENDING"
        return False
    expected_metadata = {"partial_request_id": row["id"], "partial_attempt_id": attempt["id"],
        "client_id": str(note.user_id), "note_id": str(note.id)}
    amount = Decimal(row["amount"])
    if (lookup.provider_reference != attempt["provider_reference"] or lookup.amount != amount or
            lookup.currency != "EUR" or any(lookup.metadata.get(k) != v for k, v in expected_metadata.items()) or lookup.cancelled):
        row["status"] = "REVIEW"
        raise HTTPException(409, "Le paiement bancaire ne correspond pas à la demande. Contrôle administratif nécessaire.")
    before = balance(metadata)
    now = invoices._utcnow()
    transaction = ClientManualTransaction(
        user_id=note.user_id, student_user_id=invoices._parse_optional_uuid(metadata.get("student_user_id")) or note.user_id,
        actor_user_id=None, transaction_type="PAYMENT", status="COMPLETED",
        label=f"Paiement partiel CB facture {metadata['invoice_number']}", description=f"Paiement reçu : {lookup.provider_reference}",
        category="INVOICE_RANGE_PARTIAL_PAYMENT", occurred_at=now, amount_excl_vat=-amount,
        vat_rate=Decimal("0"), vat_amount=Decimal("0"), total_incl_vat=-amount, currency="EUR",
        reference=invoices._build_manual_reference(payment_method_code="CARD_ONLINE", custom_reference=f"REF:{lookup.provider_reference}"),
        legal_entity_id=UUID(attempt["legal_entity_id"]),
    )
    db.add(transaction)
    db.flush()
    ids = metadata.setdefault("reconciled_manual_payment_ids", [])
    ids.append(str(transaction.id))
    if metadata.get("family_billing_split_group_id"):
        # Keep the prior allocated shares; add only this new settlement to this payer's invoice.
        metadata["total_to_pay_by_currency"] = {"EUR": f"{before - amount:.2f}"}
        applied = metadata.setdefault("applied_payment_totals_by_currency", {})
        applied["EUR"] = f"{Decimal(applied.get('EUR', '0')) - amount:.2f}"
        metadata.setdefault("applied_payment_lines", []).append({"date": now.strftime("%d/%m/%Y"),
            "method": "Carte bancaire", "reference": lookup.provider_reference, "amount": f"{amount:.2f}", "currency": "EUR"})
    else:
        metadata.update(invoices._synchronize_invoice_range_reconciled_payment_metadata(
            db, client_id=note.user_id, note_id=note.id, note_created_at=note.created_at, metadata=metadata,
        ))
    attempt.update(status="PAID", transaction_id=str(transaction.id), paid_at=now.isoformat())
    row.update(status="PAID", paid_at=now.isoformat())
    remaining = balance(metadata)
    if remaining != before - amount:
        raise HTTPException(409, "Écart de rapprochement du paiement. Aucun changement validé.")
    if metadata.get("invoice_status") != "CANCELLED":
        _, _, pending_checks = invoices._invoice_range_pending_check_coverage(db, metadata=metadata)
        if remaining <= 0 and not pending_checks:
            metadata["invoice_status"] = "PAID"
            metadata["paid_at"] = now.isoformat()
        else:
            metadata["invoice_status"] = "ISSUED"
    if remaining < 0 or metadata.get("invoice_status") == "CANCELLED":
        row["review_reason"] = "Paiement reçu après un autre règlement ou après annulation de la facture."
    return True


def checkout(db: Session, *, client_id: UUID, note_id: UUID, request_id: UUID, token: str) -> str:
    note, metadata, payer = load(db, client_id, note_id)
    row = find(metadata, request_id)
    verify_token(token, note, metadata, row)
    ensure_payable(metadata)
    if row["status"] not in {"READY", "PENDING"}:
        raise HTTPException(409, "Ce lien est déjà réglé, annulé ou en cours de vérification.")
    if Decimal(row["amount"]) > balance(metadata):
        raise HTTPException(409, "Le solde a changé. Contactez l’école pour obtenir un nouveau lien ; aucun paiement n’a été lancé.")
    check_other_checkout(db, note.user_id, note.id, metadata)
    for attempt in row["attempts"]:
        if attempt["status"] == "CREATING":
            raise HTTPException(409, "Paiement en cours de préparation. Actualisez dans quelques instants.")
        if attempt["status"] == "PENDING":
            result = lookup_payment(db, provider=PaymentProvider(attempt["provider"]), payment_reference=attempt["provider_reference"])
            paid = settle(db, note, metadata, row, attempt, result)
            save(db, note, metadata)
            if paid:
                return f"{invoices._frontend_base_url()}/api/v1/public/payments/partial/{client_id}/{note_id}/{request_id}?{urlencode({'token': token})}"
            if attempt["status"] == "PENDING":
                return attempt["checkout_url"]
            note, metadata, payer = load(db, client_id, note_id)
            row = find(metadata, request_id)
    _, _, entity_id = invoices._frozen_invoice_selection_for_note(db, note_id=note.id, metadata=metadata)
    entity_id = entity_id or invoices._parse_optional_uuid(metadata.get("seller_legal_entity_id"))
    if not entity_id:
        raise HTTPException(422, "Entité juridique de la facture introuvable.")
    attempt = {"id": str(uuid4()), "status": "CREATING", "legal_entity_id": str(entity_id)}
    row["attempts"].append(attempt)
    row["status"] = "CREATING"
    callback_token = token_for(note, metadata, row, attempt_id=attempt["id"])
    callback_base = f"{invoices._frontend_base_url()}/api/v1/public/payments/partial/{client_id}/{note_id}/{request_id}/attempts/{attempt['id']}"
    callback_query = urlencode({"token": callback_token})
    secret = resolve_webhook_secret(db)
    if not secret:
        raise HTTPException(503, "La validation sécurisée des paiements n’est pas configurée.")
    payload = CheckoutCreateRequest(amount=Decimal(row["amount"]), currency="EUR",
        description=f"Paiement partiel facture {metadata['invoice_number']}", customer_email=payer.email,
        success_return_url=f"{callback_base}/return?{callback_query}", cancel_return_url=f"{callback_base}/return?{callback_query}&state=cancel",
        webhook_url=with_webhook_secret(f"{callback_base}/webhook?{callback_query}", secret, param_name="secret"),
        metadata={"client_id": str(client_id), "note_id": str(note_id), "partial_request_id": row["id"], "partial_attempt_id": attempt["id"]})
    save(db, note, metadata)  # Crash/timeout cannot silently create a second checkout.
    result = create_checkout_session(db, payload, legal_entity_id=entity_id)
    note, metadata, _ = load(db, client_id, note_id)
    row = find(metadata, request_id)
    attempt = next(a for a in row["attempts"] if a["id"] == attempt["id"])
    if not result.success or not result.provider_reference or not result.checkout_url:
        uncertain = result.retryable or bool(result.provider_reference or result.checkout_url)
        row["status"] = "REVIEW" if uncertain else "READY"
        attempt["status"] = "CREATING" if uncertain else "FAILED"
        if result.provider_reference:
            attempt.update(provider=result.provider.value, provider_reference=result.provider_reference)
        save(db, note, metadata)
        raise HTTPException(502, "Le paiement n’a pas pu être préparé. Aucun règlement n’a été enregistré.")
    attempt.update(status="PENDING", provider=result.provider.value, provider_reference=result.provider_reference, checkout_url=result.checkout_url)
    row["status"] = "PENDING"
    save(db, note, metadata)
    return result.checkout_url


def cancel_request(db: Session, client_id: UUID, note_id: UUID, request_id: UUID) -> None:
    note, metadata, _ = load(db, client_id, note_id)
    row = find(metadata, request_id)
    if row["status"] == "PAID":
        raise HTTPException(409, "Cette demande a déjà été réglée.")
    for attempt in row["attempts"]:
        if attempt["status"] == "CREATING":
            raise HTTPException(409, "Une préparation bancaire doit être vérifiée avant d’annuler ce lien.")
        if attempt["status"] == "PENDING":
            result = lookup_payment(db, provider=PaymentProvider(attempt["provider"]), payment_reference=attempt["provider_reference"])
            if not result.success or result.paid or not (result.failed or result.cancelled):
                raise HTTPException(409, "Un paiement bancaire est encore ouvert ou reçu. Vérifiez-le avant d’annuler le lien.")
            attempt["status"] = "FAILED"
    row["status"] = "CANCELLED"
    save(db, note, metadata)
