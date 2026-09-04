from __future__ import annotations

import os, sys
from uuid import UUID
from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.api.routes.admin_clients import _parse_invoice_range_note_entry, send_admin_client_range_invoice_email
from app.db.session import SessionLocal
from app.models.client_record import ClientNoteEntry
from app.models.user import User, UserRole
from app.schemas.admin import AdminRangeInvoiceEmailRequest

PAYER_ID=UUID("9ea08b6e-26e8-489e-b6ad-318f9ef23c3c")

with SessionLocal() as db:
    notes=list(db.scalars(select(ClientNoteEntry).where(ClientNoteEntry.user_id==PAYER_ID).order_by(ClientNoteEntry.created_at.desc())).all())
    found=[]
    for note in notes:
        meta=_parse_invoice_range_note_entry(note)
        if meta and meta.get("invoice_number")=="PA26-0898": found.append((note,meta))
    if len(found)!=1: raise RuntimeError(f"invoice_guard_{len(found)}")
    note,meta=found[0]
    if meta.get("invoice_status")!="ISSUED": raise RuntimeError(f"status_guard_{meta.get('invoice_status')}")
    if meta.get("emailed_at"):
        print(f"ARMELLE_EMAIL|already_sent|at={meta['emailed_at']}"); raise SystemExit(0)
    actor=db.scalar(select(User).where(User.role==UserRole.ADMIN).order_by(User.created_at).limit(1))
    if actor is None: raise RuntimeError("actor_missing")
    body="""Bonjour,

À la suite du changement de créneau d’Armelle, du lundi au jeudi à 17 h à Bar-le-Duc, le calendrier annuel comporte deux cours supplémentaires.

Le créneau du lundi comprenait 31 cours, tandis que celui du jeudi en comprend 33. La facture complémentaire jointe correspond donc à ces deux cours supplémentaires, au tarif de 22 € par cours, soit un montant total de 44 €.

Nous restons à votre disposition pour toute question.

Bien cordialement,
L’équipe Piano Académie"""
    out=send_admin_client_range_invoice_email(
        client_id=PAYER_ID, note_id=note.id,
        payload=AdminRangeInvoiceEmailRequest(kind="INVOICE", subject="Piano Académie – Facture complémentaire Armelle Curin", body=body, body_format="TEXT"),
        db=db, actor=actor,
    )
    print(f"ARMELLE_EMAIL|sent|invoice=PA26-0898|recipients={','.join(out.recipients)}|message_id={out.message_id}")
