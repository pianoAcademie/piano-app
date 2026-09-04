from __future__ import annotations

import argparse, os, sys
from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.api.routes.admin_clients import create_admin_client_range_invoice, update_admin_client_range_invoice_status
from app.db.session import SessionLocal
from app.models.catalog import Booking, CourseSession
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.user import User, UserRole
from app.schemas.admin import AdminRangeInvoiceCreateRequest, AdminRangeInvoiceStatusUpdateRequest

PREFIX = "PROD_CORRECT_ARMELLE_CURIN_PRICE_20260904"
STUDENT_ID = UUID("8442aea7-6395-49c7-8150-57a0e1bb29c8")
PAYER_ID = UUID("9ea08b6e-26e8-489e-b6ad-318f9ef23c3c")
TARGET_GROUP_ID = UUID("3c0f8f87-70d5-4e1d-bc41-74c53859e317")
BAD_NOTE_ID = UUID("1de50869-9323-4bfe-8984-e3aca59abcd7")

def abort(reason): raise RuntimeError(f"{PREFIX}|abort|reason={reason}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); args=ap.parse_args()
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.role==UserRole.ADMIN).order_by(User.created_at).limit(1))
        note=db.get(ClientNoteEntry, BAD_NOTE_ID)
        if actor is None or note is None or "PA26-0895" not in note.message:
            abort("identity_guard")
        rows=db.execute(select(Booking,CourseSession).join(CourseSession).where(
            Booking.user_id==STUDENT_ID, CourseSession.recurrence_group_id==TARGET_GROUP_ID
        ).order_by(CourseSession.start_at_utc)).all()
        if len(rows)!=33: abort(f"booking_count_{len(rows)}")
        bad_lines=list(db.scalars(select(ClientInvoiceLine).where(ClientInvoiceLine.note_id==BAD_NOTE_ID)).all())
        if len(bad_lines)!=2 or sum((Decimal(x.total_incl_vat) for x in bad_lines),Decimal())!=Decimal("46.80"):
            abort("bad_invoice_changed")
        extras=[b for b,s in rows if b.id in {x.source_payment_id for x in bad_lines}]
        if len(extras)!=2: abort("extra_booking_guard")
        print(f"{PREFIX}|audit|bookings=33|bad_invoice=PA26-0895|bad_total=46.80|replacement=44.00|apply={args.apply}")
        if not args.apply: db.rollback(); return
        # Cancel first so the two booking lines are available for a replacement invoice.
        update_admin_client_range_invoice_status(PAYER_ID, BAD_NOTE_ID, AdminRangeInvoiceStatusUpdateRequest(status="CANCELLED"), db=db, _=actor)
        with SessionLocal() as db2:
            locked=db2.execute(select(Booking,CourseSession).join(CourseSession).where(
                Booking.user_id==STUDENT_ID, CourseSession.recurrence_group_id==TARGET_GROUP_ID
            ).order_by(CourseSession.start_at_utc).with_for_update()).all()
            extra_ids={b.id for b in extras}
            for booking, _ in locked:
                booking.price_excl_vat_snapshot=Decimal("18.33")
                booking.vat_rate_snapshot=Decimal("20.00")
                booking.vat_amount_snapshot=Decimal("3.67")
                booking.total_incl_vat_snapshot=Decimal("22.00")
                booking.pricing_snapshot_locked=True
                db2.add(booking)
            db2.commit()
        with SessionLocal() as db3:
            actor3=db3.get(User,actor.id)
            invoice=create_admin_client_range_invoice(PAYER_ID, AdminRangeInvoiceCreateRequest(
                issued_date=date(2026,9,4), due_date=date(2026,9,4),
                start_date=date(2027,6,17), end_date=date(2027,6,24),
                selected_payment_keys=[f"BOOKING:{bid}" for bid in sorted(extra_ids,key=str)],
                auto_include_previous_balance=False,
                public_note="Facture complémentaire liée au transfert du lundi au jeudi : 32 cours sont prévus le jeudi au lieu de 31 le lundi.",
                private_note="Remplace la facture PA26-0895 annulée; correction du tarif contractuel à 22 EUR par séance; aucun email envoyé.",
            ), db=db3, actor=actor3)
            if invoice.totals_by_currency.get("EUR")!="44.00": abort(f"replacement_total_{invoice.totals_by_currency}")
            print(f"{PREFIX}|summary|result=applied|cancelled=PA26-0895|replacement={invoice.invoice_number}|total=44.00|bookings_at_22=33|email_sent=False")

if __name__=="__main__": main()
