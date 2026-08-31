from __future__ import annotations

import hmac
from decimal import Decimal
from html import escape
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.db.session import SessionLocal
from app.models.user import User, UserRole
from app.services import invoice_partial_payments as service

router = APIRouter()
ADMIN = "/admin/clients/{client_id}/invoices/range/{note_id}/partial-payments"
PUBLIC = "/public/payments/partial/{client_id}/{note_id}/{request_id}"


class CreateRequest(BaseModel):
    request_id: UUID
    amount: Decimal = Field(ge=Decimal("1.00"), max_digits=12, decimal_places=2)


@router.get(ADMIN)
def context(client_id: UUID, note_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_roles(UserRole.ADMIN))) -> dict:
    note, metadata, payer = service.load(db, client_id, note_id)
    available = max(Decimal("0"), service.balance(metadata))
    rows = [{k: r.get(k) for k in ("id", "amount", "status", "created_at", "expires_at", "sent_at", "paid_at", "email_error", "recipients")}
        for r in service.requests(metadata)]
    active_ids = {r["id"] for r in service.active_requests(metadata)}
    for r in rows:
        r["active"] = r["id"] in active_ids
    return {"invoice_number": metadata["invoice_number"], "invoice_status": metadata["invoice_status"],
        "invoice_total": metadata["totals_by_currency"]["EUR"], "balance": f"{available:.2f}", "currency": "EUR",
        "recipients": service.recipients_for(db, payer), "requests": rows}


@router.post(ADMIN)
def create(client_id: UUID, note_id: UUID, payload: CreateRequest, db: Session = Depends(get_db), actor: User = Depends(require_roles(UserRole.ADMIN))) -> dict:
    return service.create_request(db, client_id=client_id, note_id=note_id,
        request_id=payload.request_id, amount=payload.amount, actor=actor)


@router.post(ADMIN + "/{request_id}/cancel")
def cancel(client_id: UUID, note_id: UUID, request_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_roles(UserRole.ADMIN))) -> dict:
    service.cancel_request(db, client_id, note_id, request_id)
    return {"cancelled": True}


def receipt_task(client_id: UUID, note_id: UUID, request_id: UUID) -> None:
    with SessionLocal() as db:
        note, metadata, payer = service.load(db, client_id, note_id)
        row = service.find(metadata, request_id)
        if row["status"] != "PAID" or row.get("receipt_sent_at"):
            return
        try:
            service.send_message(db, note, metadata, row, payer, receipt=True)
        except Exception:
            row["receipt_error"] = "Envoi du reçu à vérifier dans le journal des communications."
        service.save(db, note, metadata)


def callback(db: Session, *, client_id: UUID, note_id: UUID, request_id: UUID, attempt_id: UUID, token: str | None,
             background_tasks: BackgroundTasks) -> dict:
    note, metadata, _ = service.load(db, client_id, note_id)
    row = service.find(metadata, request_id)
    if token is not None:  # None is used only by the verified, server-side PSP dispatcher.
        service.verify_token(token, note, metadata, row, attempt_id=str(attempt_id))
    attempt = next((a for a in row["attempts"] if a["id"] == str(attempt_id)), None)
    if not attempt or not attempt.get("provider_reference"):
        raise HTTPException(503, "La référence bancaire n’est pas encore disponible. Réessayez dans quelques instants.")
    if attempt.get("transaction_id"):
        paid = True
    else:
        lookup = service.lookup_payment(db, provider=service.PaymentProvider(attempt["provider"]), payment_reference=attempt["provider_reference"])
        paid = service.settle(db, note, metadata, row, attempt, lookup)
        service.save(db, note, metadata)
    if paid:
        background_tasks.add_task(receipt_task, client_id, note_id, request_id)
    return {"paid": paid, "amount": row["amount"], "remaining": f"{max(Decimal('0'), service.balance(metadata)):.2f}",
        "invoice_number": metadata["invoice_number"], "request_id": row["id"]}


def page(*, title: str, message: str, details: list[tuple[str, str]], form_url: str | None = None) -> HTMLResponse:
    rows = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in details)
    form = (f'<form method="post" action="{escape(form_url, quote=True)}"><button type="submit">Continuer vers le paiement sécurisé</button></form>' if form_url else "")
    html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)} — Piano Académie</title><style>
    *{{box-sizing:border-box}}body{{margin:0;padding:24px 12px;background:#f4f5f8;font:16px/1.5 system-ui;color:#172033}}
    main{{max-width:620px;margin:auto;background:white;border-radius:16px;overflow:hidden;border:1px solid #ddd}}
    header{{background:#172033;color:#e4b85d;padding:24px}}h1{{font-size:26px;color:white;margin:10px 0}}section{{padding:24px}}
    dl{{display:grid;grid-template-columns:1fr 1fr;background:#f8fafc;padding:16px;gap:12px}}dd{{margin:0;font-weight:700}}
    button{{border:0;border-radius:10px;background:#c98224;color:white;padding:16px;font-size:16px;cursor:pointer;width:100%}}
    </style></head><body><main><header>PIANO ACADÉMIE<h1>{escape(title)}</h1></header><section><p>{escape(message)}</p><dl>{rows}</dl>{form}</section></main></body></html>'''
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get(PUBLIC)
def landing(client_id: UUID, note_id: UUID, request_id: UUID, background_tasks: BackgroundTasks,
            token: str = Query(min_length=24, max_length=4096), db: Session = Depends(get_db)) -> HTMLResponse:
    note, metadata, _ = service.load(db, client_id, note_id)
    row = service.find(metadata, request_id)
    service.verify_token(token, note, metadata, row)
    paid = row["status"] == "PAID"
    available = max(Decimal("0"), service.balance(metadata))
    valid = not paid and row["status"] in {"READY", "PENDING"} and metadata["invoice_status"] == "ISSUED" and Decimal(row["amount"]) <= available
    if paid:
        background_tasks.add_task(receipt_task, client_id, note_id, request_id)
    return page(title="Paiement confirmé" if paid else "Paiement partiel",
        message=("Votre règlement a été enregistré. Le solde restant figure ci-dessous." if paid else
            "Vous réglez uniquement le montant demandé ci-dessous, sur votre facture existante." if valid else
            "Ce lien n’est plus payable ou nécessite une vérification. Contactez l’école ; aucun nouveau règlement n’est lancé."),
        details=[("Facture", metadata["invoice_number"]), ("Montant reçu" if paid else "À régler par carte", service.money(Decimal(row["amount"]))),
            ("Solde restant" if paid else "Solde après paiement confirmé", service.money(available if paid or not valid else available - Decimal(row["amount"])))],
        form_url=service.public_url(note, metadata, row).replace("?", "/card?", 1) if valid else None)


@router.post(PUBLIC + "/card")
def card(client_id: UUID, note_id: UUID, request_id: UUID, token: str = Query(min_length=24, max_length=4096), db: Session = Depends(get_db)) -> RedirectResponse:
    return RedirectResponse(service.checkout(db, client_id=client_id, note_id=note_id, request_id=request_id, token=token), status_code=303)


@router.post(PUBLIC + "/attempts/{attempt_id}/webhook")
def webhook(client_id: UUID, note_id: UUID, request_id: UUID, attempt_id: UUID, background_tasks: BackgroundTasks,
            token: str = Query(min_length=24, max_length=4096), secret: str = Query(default=""), db: Session = Depends(get_db)) -> dict:
    configured = service.resolve_webhook_secret(db)
    if not configured or not hmac.compare_digest(secret, configured):
        raise HTTPException(401, "Invalid webhook secret")
    return callback(db, client_id=client_id, note_id=note_id, request_id=request_id, attempt_id=attempt_id, token=token, background_tasks=background_tasks)


@router.get(PUBLIC + "/attempts/{attempt_id}/return")
def payment_return(client_id: UUID, note_id: UUID, request_id: UUID, attempt_id: UUID, background_tasks: BackgroundTasks,
                   token: str = Query(min_length=24, max_length=4096), state: str = Query(default="success"), db: Session = Depends(get_db)) -> HTMLResponse:
    # Browser success/cancel is never proof of payment; always verify the stored PSP attempt.
    result = callback(db, client_id=client_id, note_id=note_id, request_id=request_id, attempt_id=attempt_id, token=token, background_tasks=background_tasks)
    return page(title="Paiement confirmé" if result["paid"] else "Paiement non confirmé",
        message="Votre paiement a bien été enregistré." if result["paid"] else "Aucun paiement confirmé à ce stade. Vous pouvez réouvrir le lien reçu par courriel pour vérifier ou réessayer.",
        details=[("Facture", result["invoice_number"]), ("Montant demandé", service.money(Decimal(result["amount"]))),
            ("Solde restant", service.money(Decimal(result["remaining"])))])
