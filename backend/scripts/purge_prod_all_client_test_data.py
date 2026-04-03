from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import delete, func, or_, select

from app.db.session import SessionLocal
from app.models.catalog import Booking
from app.models.client_group import ClientGroupMembership
from app.models.client_record import (
    ClientAutoInvoiceOccurrence,
    ClientAutoInvoiceRule,
    ClientInvoiceLine,
    ClientManualTransaction,
    ClientNoteEntry,
    ClientPaymentRefund,
    PaymentReceipt,
)
from app.models.family import ClientFamilyLink
from app.models.ops import CommunicationLog
from app.models.plan import ClientPlanSubscription
from app.models.product_catalog import ProductRequest
from app.models.quote import (
    Prospect,
    Quote,
    QuoteAcceptanceFollowup,
    QuoteDocumentSnapshot,
    QuoteEmailOutbox,
    QuoteEvent,
    QuoteLine,
)
from app.models.typeform_intake import TypeformIntake
from app.models.user import User, UserRole

SCRIPT_PREFIX = "PROD_ALL_CLIENT_TEST_DATA_PURGE"


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _count_scalar(db, stmt) -> int:
    value = db.scalar(stmt)
    return int(value or 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Purge all client-side test data from production: client accounts, families, bookings, "
            "payments, invoices, prospects, quotes, and typeform intakes."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the deletion. Without this flag, the script runs in dry-run mode only.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        target_clients = db.scalars(
            select(User)
            .where(User.role == UserRole.CLIENT)
            .order_by(User.created_at.asc(), User.email.asc())
            .with_for_update()
        ).all()
        target_user_ids = {client.id for client in target_clients}
        target_emails = {_normalize_email(client.email) for client in target_clients}
        target_emails.discard(None)

        target_prospects = db.scalars(select(Prospect).order_by(Prospect.created_at.asc())).all()
        target_prospect_ids = {prospect.id for prospect in target_prospects}
        target_prospect_emails = {_normalize_email(prospect.email) for prospect in target_prospects}
        target_prospect_emails.discard(None)

        target_quotes = db.scalars(select(Quote).order_by(Quote.created_at.asc())).all()
        target_quote_ids = {quote.id for quote in target_quotes}

        all_contact_emails = set(target_emails) | set(target_prospect_emails)

        note_ids_subquery = select(ClientNoteEntry.id).where(ClientNoteEntry.user_id.in_(target_user_ids))
        auto_rule_ids_subquery = select(ClientAutoInvoiceRule.id).where(ClientAutoInvoiceRule.user_id.in_(target_user_ids))
        communication_filter = or_(
            CommunicationLog.recipient_user_id.in_(target_user_ids),
            CommunicationLog.sender_user_id.in_(target_user_ids),
            func.lower(CommunicationLog.recipient).in_(all_contact_emails),
        )

        summary = Counter()
        summary["clients"] = len(target_clients)
        summary["family_links"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientFamilyLink).where(
                or_(
                    ClientFamilyLink.adult_user_id.in_(target_user_ids),
                    ClientFamilyLink.child_user_id.in_(target_user_ids),
                )
            ),
        )
        summary["bookings"] = _count_scalar(
            db,
            select(func.count()).select_from(Booking).where(Booking.user_id.in_(target_user_ids)),
        )
        summary["payment_receipts"] = _count_scalar(
            db,
            select(func.count()).select_from(PaymentReceipt).where(
                or_(
                    PaymentReceipt.customer_id.in_(target_user_ids),
                    PaymentReceipt.student_id.in_(target_user_ids),
                )
            ),
        )
        summary["invoice_notes"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientNoteEntry).where(ClientNoteEntry.user_id.in_(target_user_ids)),
        )
        summary["invoice_lines"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientInvoiceLine).where(ClientInvoiceLine.note_id.in_(note_ids_subquery)),
        )
        summary["manual_transactions"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientManualTransaction).where(
                or_(
                    ClientManualTransaction.user_id.in_(target_user_ids),
                    ClientManualTransaction.student_user_id.in_(target_user_ids),
                )
            ),
        )
        summary["payment_refunds"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientPaymentRefund).where(ClientPaymentRefund.user_id.in_(target_user_ids)),
        )
        summary["subscriptions"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientPlanSubscription).where(ClientPlanSubscription.user_id.in_(target_user_ids)),
        )
        summary["group_memberships"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientGroupMembership).where(ClientGroupMembership.user_id.in_(target_user_ids)),
        )
        summary["auto_invoice_rules"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientAutoInvoiceRule).where(ClientAutoInvoiceRule.user_id.in_(target_user_ids)),
        )
        summary["auto_invoice_occurrences"] = _count_scalar(
            db,
            select(func.count()).select_from(ClientAutoInvoiceOccurrence).where(
                ClientAutoInvoiceOccurrence.rule_id.in_(auto_rule_ids_subquery)
            ),
        )
        summary["product_requests"] = _count_scalar(
            db,
            select(func.count()).select_from(ProductRequest).where(ProductRequest.student_user_id.in_(target_user_ids)),
        )
        summary["communication_logs"] = _count_scalar(
            db,
            select(func.count()).select_from(CommunicationLog).where(communication_filter),
        )
        summary["prospects"] = len(target_prospects)
        summary["quotes"] = len(target_quotes)
        summary["quote_document_snapshots"] = _count_scalar(
            db,
            select(func.count()).select_from(QuoteDocumentSnapshot).where(QuoteDocumentSnapshot.quote_id.in_(target_quote_ids)),
        )
        summary["quote_lines"] = _count_scalar(
            db,
            select(func.count()).select_from(QuoteLine).where(QuoteLine.quote_id.in_(target_quote_ids)),
        )
        summary["quote_events"] = _count_scalar(
            db,
            select(func.count()).select_from(QuoteEvent).where(QuoteEvent.quote_id.in_(target_quote_ids)),
        )
        summary["quote_email_outbox"] = _count_scalar(
            db,
            select(func.count()).select_from(QuoteEmailOutbox).where(QuoteEmailOutbox.quote_id.in_(target_quote_ids)),
        )
        summary["quote_acceptance_followups"] = _count_scalar(
            db,
            select(func.count()).select_from(QuoteAcceptanceFollowup).where(
                QuoteAcceptanceFollowup.quote_id.in_(target_quote_ids)
            ),
        )
        summary["typeform_intakes"] = _count_scalar(
            db,
            select(func.count()).select_from(TypeformIntake),
        )

        mode = "apply" if args.apply else "dry-run"
        print(f"[{SCRIPT_PREFIX}] mode={mode}")
        print(f"[{SCRIPT_PREFIX}] scope=all-client-test-data")
        for key in [
            "clients",
            "family_links",
            "bookings",
            "payment_receipts",
            "invoice_notes",
            "invoice_lines",
            "manual_transactions",
            "payment_refunds",
            "subscriptions",
            "group_memberships",
            "auto_invoice_rules",
            "auto_invoice_occurrences",
            "product_requests",
            "communication_logs",
            "prospects",
            "quotes",
            "quote_document_snapshots",
            "quote_lines",
            "quote_events",
            "quote_email_outbox",
            "quote_acceptance_followups",
            "typeform_intakes",
        ]:
            print(f"[{SCRIPT_PREFIX}] {key}={summary[key]}")

        if not args.apply:
            db.rollback()
            return

        deleted_communication_logs = db.execute(delete(CommunicationLog).where(communication_filter)).rowcount or 0
        deleted_typeform_intakes = db.execute(delete(TypeformIntake)).rowcount or 0
        deleted_quotes = db.execute(delete(Quote).where(Quote.id.in_(target_quote_ids))).rowcount or 0
        deleted_prospects = db.execute(delete(Prospect).where(Prospect.id.in_(target_prospect_ids))).rowcount or 0

        for client in target_clients:
            db.delete(client)
        db.commit()

    print(f"[{SCRIPT_PREFIX}] deleted_communication_logs={deleted_communication_logs}")
    print(f"[{SCRIPT_PREFIX}] deleted_typeform_intakes={deleted_typeform_intakes}")
    print(f"[{SCRIPT_PREFIX}] deleted_quotes={deleted_quotes}")
    print(f"[{SCRIPT_PREFIX}] deleted_prospects={deleted_prospects}")
    print(f"[{SCRIPT_PREFIX}] purge_complete=true")


if __name__ == "__main__":
    main()
