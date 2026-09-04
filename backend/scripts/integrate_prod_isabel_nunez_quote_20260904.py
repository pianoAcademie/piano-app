"""Integrate Isabel Nunez after repairing the legacy parent-email placeholder.

Dry-run by default. Pass ``--apply`` after deploying the child identity fix.
"""

from __future__ import annotations

import argparse
from uuid import UUID

from sqlalchemy import select

from app.api.routes.quotes import _execute_quote_followup_transformation
from app.db.session import SessionLocal
from app.models.family import ClientFamilyLink
from app.models.quote import Prospect, Quote, QuoteAcceptanceFollowup
from app.models.user import ClientKind, User, UserRole


QUOTE_NUMBER = "DV-20260902165534-5787"
EXPECTED_QUOTE_ID = UUID("3608d936-3009-496b-bbd9-9e1483c6723f")
EXPECTED_PROSPECT_ID = UUID("59973acd-de49-4f62-b467-ec2b716c2871")
EXPECTED_PARENT_ID = UUID("9c2b80fa-9d6b-4344-a5cf-afd3682637c3")
EXPECTED_ACTOR_ID = UUID("aa171301-2516-4e34-b08f-a74fdef41a2d")


def integrate(*, apply: bool) -> None:
    with SessionLocal() as db:
        quote = db.scalar(select(Quote).where(Quote.quote_number == QUOTE_NUMBER).with_for_update())
        if quote is None or quote.id != EXPECTED_QUOTE_ID:
            raise RuntimeError(f"Unexpected quote for {QUOTE_NUMBER}: {getattr(quote, 'id', None)}")
        if str(quote.status or "").strip().lower() != "approved":
            raise RuntimeError(f"Refusing to integrate quote in status {quote.status}")

        prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id).with_for_update())
        if prospect is None or prospect.id != EXPECTED_PROSPECT_ID:
            raise RuntimeError(f"Unexpected quote prospect: {getattr(prospect, 'id', None)}")
        if (prospect.first_name or "").strip().lower() != "isabel" or (prospect.last_name or "").strip().lower() != "nunez":
            raise RuntimeError(f"Unexpected prospect identity: {prospect.first_name} {prospect.last_name}")

        parent = db.scalar(select(User).where(User.id == EXPECTED_PARENT_ID).with_for_update())
        if parent is None or parent.client_kind != ClientKind.ADULT:
            raise RuntimeError("Expected Daniela Nunez adult billing account is missing")
        if prospect.linked_client_id not in {None, parent.id}:
            linked = db.get(User, prospect.linked_client_id)
            if linked is None or linked.client_kind != ClientKind.CHILD:
                raise RuntimeError(f"Prospect points to an unexpected client: {prospect.linked_client_id}")

        followup = db.scalar(
            select(QuoteAcceptanceFollowup)
            .where(QuoteAcceptanceFollowup.quote_id == quote.id)
            .with_for_update()
        )
        if followup is None:
            raise RuntimeError("Quote follow-up is missing")
        execution = dict((followup.payload or {}).get("quote_to_enrollment_execution") or {})
        if str(execution.get("status") or "").strip().lower() == "executed":
            print({"quote": QUOTE_NUMBER, "mode": "already-integrated", "execution": execution})
            db.rollback()
            return

        transformation = dict((followup.payload or {}).get("quote_to_enrollment") or {})
        client_resolution = dict(transformation.get("clientResolution") or {})
        if client_resolution.get("mode") != "new_child_existing_parent":
            raise RuntimeError(f"Unexpected client resolution: {client_resolution}")
        if str(client_resolution.get("selectedParentClientId") or "") != str(EXPECTED_PARENT_ID):
            raise RuntimeError(f"Unexpected selected parent: {client_resolution.get('selectedParentClientId')}")

        actor = db.scalar(select(User).where(User.id == EXPECTED_ACTOR_ID).with_for_update())
        if actor is None or actor.role != UserRole.ADMIN:
            raise RuntimeError("Expected admin actor is missing")

        result = _execute_quote_followup_transformation(
            db,
            quote=quote,
            followup=followup,
            current_user=actor,
        )
        db.flush()

        child_id = UUID(str(result.get("student_client_id")))
        child = db.get(User, child_id)
        if child is None or child.client_kind != ClientKind.CHILD:
            raise RuntimeError(f"Transformation did not produce a child client: {child_id}")
        if (child.first_name or "").strip().lower() != "isabel" or (child.last_name or "").strip().lower() != "nunez":
            raise RuntimeError(f"Unexpected transformed child: {child.first_name} {child.last_name}")
        family_link = db.scalar(
            select(ClientFamilyLink).where(
                ClientFamilyLink.adult_user_id == parent.id,
                ClientFamilyLink.child_user_id == child.id,
            )
        )
        if family_link is None or not family_link.is_billing_recipient:
            raise RuntimeError("Isabel was not linked to Daniela as billing recipient")

        summary = {
            "quote": QUOTE_NUMBER,
            "mode": "apply" if apply else "dry-run",
            "student": f"{child.first_name} {child.last_name}",
            "student_client_id": str(child.id),
            "billing_client_id": str(parent.id),
            "bookings": len(result.get("created_booking_ids") or []),
            "transactions": len(result.get("created_transaction_ids") or []),
            "invoices": len(result.get("created_invoice_note_ids") or []),
            "annual_invoices": len(result.get("created_annual_invoice_note_ids") or []),
            "subscription_id": result.get("subscription_id"),
        }
        print(summary)

        if apply:
            db.commit()
        else:
            db.rollback()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    integrate(apply=parser.parse_args().apply)
