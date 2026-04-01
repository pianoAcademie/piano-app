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
from app.models.user import User, UserRole

SCRIPT_PREFIX = "PROD_CLIENT_FAMILY_PURGE"


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _collect_connected_family_user_ids(db, root_user_id: UUID) -> set[UUID]:
    connected: set[UUID] = {root_user_id}
    frontier: set[UUID] = {root_user_id}

    while frontier:
        rows = db.execute(
            select(ClientFamilyLink.adult_user_id, ClientFamilyLink.child_user_id).where(
                or_(
                    ClientFamilyLink.adult_user_id.in_(frontier),
                    ClientFamilyLink.child_user_id.in_(frontier),
                )
            )
        ).all()
        discovered: set[UUID] = set()
        for adult_user_id, child_user_id in rows:
            discovered.add(adult_user_id)
            discovered.add(child_user_id)
        frontier = discovered - connected
        connected.update(discovered)

    return connected


def _count_scalar(db, stmt) -> int:
    value = db.scalar(stmt)
    return int(value or 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Purge a production client, the whole linked family graph, and all related bookings/invoices/payments.",
    )
    parser.add_argument("--email", required=True, help="Root client email to purge with the whole family graph.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the deletion. Without this flag, the script runs in dry-run mode only.",
    )
    args = parser.parse_args()

    normalized_email = _normalize_email(args.email)

    with SessionLocal() as db:
        root_client = db.scalar(
            select(User)
            .where(
                func.lower(User.email) == normalized_email,
                User.role == UserRole.CLIENT,
            )
            .with_for_update()
        )
        if root_client is None:
            raise SystemExit(f"[{SCRIPT_PREFIX}] root client not found for email={normalized_email}")

        target_user_ids = _collect_connected_family_user_ids(db, root_client.id)
        target_clients = db.scalars(
            select(User)
            .where(
                User.id.in_(target_user_ids),
                User.role == UserRole.CLIENT,
            )
            .order_by(User.created_at.asc(), User.email.asc())
            .with_for_update()
        ).all()
        target_user_ids = {client.id for client in target_clients}
        target_emails = {_normalize_email(client.email) for client in target_clients}

        if not target_clients:
            raise SystemExit(f"[{SCRIPT_PREFIX}] no client rows found for connected family of email={normalized_email}")

        note_ids_subquery = select(ClientNoteEntry.id).where(ClientNoteEntry.user_id.in_(target_user_ids))
        auto_rule_ids_subquery = select(ClientAutoInvoiceRule.id).where(ClientAutoInvoiceRule.user_id.in_(target_user_ids))

        communication_filter = or_(
            CommunicationLog.recipient_user_id.in_(target_user_ids),
            CommunicationLog.sender_user_id.in_(target_user_ids),
            func.lower(CommunicationLog.recipient).in_(target_emails),
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
        summary["communication_logs"] = _count_scalar(
            db,
            select(func.count()).select_from(CommunicationLog).where(communication_filter),
        )

        mode = "apply" if args.apply else "dry-run"
        print(f"[{SCRIPT_PREFIX}] mode={mode}")
        print(f"[{SCRIPT_PREFIX}] root_email={normalized_email}")
        for client in target_clients:
            full_name = " ".join(part for part in [client.first_name or "", client.last_name or ""] if part).strip() or "-"
            print(
                f"[{SCRIPT_PREFIX}] client={client.id}|email={client.email}|name={full_name}|"
                f"kind={client.client_kind.value}|status={client.client_status.value}"
            )
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
            "communication_logs",
        ]:
            print(f"[{SCRIPT_PREFIX}] {key}={summary[key]}")

        if not args.apply:
            db.rollback()
            return

        deleted_communication_logs = db.execute(delete(CommunicationLog).where(communication_filter)).rowcount or 0
        for client in target_clients:
            db.delete(client)
        db.commit()

    print(f"[{SCRIPT_PREFIX}] deleted_communication_logs={deleted_communication_logs}")
    print(f"[{SCRIPT_PREFIX}] purge_complete=true")


if __name__ == "__main__":
    main()
