from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import timedelta
from uuid import UUID

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.api.routes.quotes import (
    _ensure_public_token,
    _freeze_quote_document_snapshot,
    _load_quote,
    _load_quote_lines,
    _resolve_recipient_email,
    _utcnow,
    cancel_quote,
    public_approve_quote,
    public_change_request_quote,
    public_reject_quote,
)
from app.api.routes.typeform_intakes import (
    _answer,
    _demo_payload,
    _ingest_typeform_payload,
    create_draft_quote_from_typeform_intake,
    seed_typeform_demo,
)
from app.db.session import SessionLocal
from app.models.quote import Quote, QuoteEvent
from app.models.typeform_intake import TypeformIntake
from app.models.user import User, UserRole
from app.schemas.quote import QuoteCancelRequest, QuoteChangeRequestIn

LOCAL_FRONTEND_BASE = "http://localhost:3000"


@dataclass
class SeededCase:
    label: str
    category: str
    status: str
    intake_id: str | None = None
    quote_id: str | None = None
    quote_number: str | None = None
    admin_url: str | None = None
    public_url: str | None = None
    notes: str | None = None


def _admin_url(quote_id: UUID) -> str:
    return f"{LOCAL_FRONTEND_BASE}/admin/quotes/{quote_id}"


def _public_url(quote: Quote) -> str | None:
    if not quote.public_token:
        return None
    return f"{LOCAL_FRONTEND_BASE}/q/{quote.id}?t={quote.public_token}"


def _require_admin(db) -> User:
    admin = db.scalar(select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True)).limit(1))
    if admin is None:
        raise RuntimeError("Aucun utilisateur admin actif trouve en base locale")
    return admin


def _create_intake(db, *, form_id: str, response_id: str, answers: list[dict[str, object]]) -> TypeformIntake:
    payload = _demo_payload(form_id=form_id, response_id=response_id, answers=answers)
    return _ingest_typeform_payload(db, payload)


def _create_quote_from_intake(db, *, intake_id: UUID, current_user: User) -> Quote:
    result = create_draft_quote_from_typeform_intake(intake_id=intake_id, db=db, current_user=current_user)
    return _load_quote(db, result.quote_id, lock=False)


def _mark_quote_sent_for_demo(db, *, quote: Quote, actor: User, expires_in: timedelta | None = None) -> Quote:
    now = _utcnow()
    _ensure_public_token(quote)
    lines = _load_quote_lines(db, quote.id)
    recipient = _resolve_recipient_email(db, quote) or "demo@piano-academie.test"
    _freeze_quote_document_snapshot(db, quote=quote, lines=lines, state="frozen")
    quote.status = "sent"
    quote.sent_at = now
    quote.expires_at = now + (expires_in or timedelta(days=int(quote.expiry_days or 10)))
    quote.updated_at = now
    quote.meta = {
        **(quote.meta or {}),
        "recipient_email": recipient,
        "demo_seed": True,
    }
    db.add(quote)
    db.add(
        QuoteEvent(
            quote_id=quote.id,
            event_type="quote_demo_seed_marked_sent",
            actor_type="admin",
            actor_id=actor.id,
            payload={"recipient_email": recipient},
            created_at=now,
        )
    )
    db.commit()
    db.refresh(quote)
    return quote


def _case_from_quote(label: str, category: str, quote: Quote, *, notes: str | None = None) -> SeededCase:
    return SeededCase(
        label=label,
        category=category,
        status=str(quote.status or "").strip(),
        intake_id=None,
        quote_id=str(quote.id),
        quote_number=quote.quote_number,
        admin_url=_admin_url(quote.id),
        public_url=_public_url(quote),
        notes=notes,
    )


def main() -> None:
    batch = _utcnow().strftime("%Y%m%d-%H%M%S")
    with SessionLocal() as db:
        admin = _require_admin(db)
        seed_typeform_demo(db=db, _=admin)

        cases: list[SeededCase] = []

        # Intake only: matching required (multiple eligible slots)
        intake_matching = _create_intake(
            db,
            form_id="tf_paris_eveil_2025_pompe",
            response_id=f"demo_quote_case_matching_{batch}",
            answers=[
                _answer("prenom_parent", "Maya"),
                _answer("nom_parent", f"Matching{batch[-4:]}"),
                _answer("email_parent", f"maya.matching.{batch}@piano-academie.test"),
                _answer("telephone_parent", "+33699001001"),
                _answer("prenom_enfant", "Noa"),
                _answer("nom_enfant", f"Matching{batch[-4:]}"),
                _answer("date_naissance_enfant", "2020-09-03"),
                _answer("jours_souhaites", ["Mercredi", "Samedi"]),
                _answer("horaires_souhaites", ["10:00"]),
                _answer("formule_souhaitee", "Eveil musical"),
                _answer("commentaires", f"CASE MATCHING REQUIRED {batch}"),
            ],
        )
        cases.append(
            SeededCase(
                label="Intake matching requis",
                category="intake",
                status=intake_matching.intake_status,
                intake_id=str(intake_matching.id),
                notes="Plusieurs creneaux possibles, devis non cree.",
            )
        )

        # Intake only: blocked (no relevant slot)
        intake_blocked = _create_intake(
            db,
            form_id="tf_paris_teen_2025_richelieu",
            response_id=f"demo_quote_case_blocked_{batch}",
            answers=[
                _answer("parent_first_name", "Hugo"),
                _answer("parent_last_name", f"Blocked{batch[-4:]}"),
                _answer("parent_email", f"hugo.blocked.{batch}@piano-academie.test"),
                _answer("parent_phone", "+33699001002"),
                _answer("child_first_name", "Leo"),
                _answer("child_last_name", f"Blocked{batch[-4:]}"),
                _answer("child_birth_date", "2011-01-19"),
                _answer("requested_days", ["Lundi"]),
                _answer("requested_times", ["21:00"]),
                _answer("requested_formula_type", "Cours ado"),
                _answer("notes", f"CASE BLOCKED {batch}"),
            ],
        )
        cases.append(
            SeededCase(
                label="Intake bloquee",
                category="intake",
                status=intake_blocked.intake_status,
                intake_id=str(intake_blocked.id),
                notes="Aucun creneau compatible, devis non cree.",
            )
        )

        def child_answers(parent_first: str, parent_last: str, child_first: str, child_last: str, email_prefix: str) -> list[dict[str, object]]:
            return [
                _answer("parent_first_name", parent_first),
                _answer("parent_last_name", parent_last),
                _answer("parent_email", f"{email_prefix}.{batch}@piano-academie.test"),
                _answer("parent_phone", "+33699420170"),
                _answer("child_first_name", child_first),
                _answer("child_last_name", child_last),
                _answer("child_birth_date", "2016-03-15"),
                _answer("requested_days", ["Mardi"]),
                _answer("requested_times", ["17:30"]),
                _answer("requested_formula_type", "Cours collectif enfant"),
                _answer("notes", f"CASE {email_prefix.upper()} {batch}"),
            ]

        quote_specs = [
            ("Devis brouillon", "draft", "tf_paris_child_2025_richelieu", f"demo_quote_case_draft_{batch}", child_answers("Alice", "Brouillon", "Nina", "Brouillon", "alice.brouillon")),
            ("Devis envoye", "sent", "tf_paris_child_2025_richelieu", f"demo_quote_case_sent_{batch}", child_answers("Benoit", "Envoye", "Leo", "Envoye", "benoit.envoye")),
            ("Devis approuve", "approved", "tf_paris_child_2025_richelieu", f"demo_quote_case_approved_{batch}", child_answers("Chloe", "Approuvee", "Milo", "Approuve", "chloe.approuvee")),
            ("Demande de modification", "change_requested", "tf_paris_child_2025_richelieu", f"demo_quote_case_change_{batch}", child_answers("Diane", "Modification", "Lila", "Modification", "diane.modification")),
            ("Devis rejete", "rejected", "tf_paris_child_2025_richelieu", f"demo_quote_case_rejected_{batch}", child_answers("Evan", "Refus", "Nora", "Refus", "evan.refus")),
            ("Devis annule", "cancelled", "tf_paris_child_2025_richelieu", f"demo_quote_case_cancelled_{batch}", child_answers("Fanny", "Annule", "Tom", "Annule", "fanny.annule")),
            ("Relance a J-1", "reminder_due", "tf_paris_child_2025_richelieu", f"demo_quote_case_reminder_{batch}", child_answers("Gisele", "Relance", "Adam", "Relance", "gisele.relance")),
            (
                "Client existant brouillon",
                "active_client",
                "tf_bld_adult_2025",
                f"demo_quote_case_active_client_{batch}",
                [
                    _answer("adult_first_name", "Julien"),
                    _answer("adult_last_name", "Bernard"),
                    _answer("adult_email", "julien.bernard.demo@piano-academie.test"),
                    _answer("adult_phone", "+33600000022"),
                    _answer("requested_days", ["Jeudi"]),
                    _answer("requested_times", ["19:00"]),
                    _answer("requested_formula_type", "Cours adulte individuel"),
                    _answer("notes", f"CASE ACTIVE CLIENT {batch}"),
                ],
            ),
        ]

        for label, scenario, form_id, response_id, answers in quote_specs:
            intake = _create_intake(db, form_id=form_id, response_id=response_id, answers=answers)
            quote = _create_quote_from_intake(db, intake_id=intake.id, current_user=admin)
            quote.meta = {
                **(quote.meta or {}),
                "demo_case_label": label,
                "demo_case_key": scenario,
                "demo_case_batch": batch,
            }
            db.add(quote)
            db.commit()
            db.refresh(quote)

            if scenario == "sent":
                quote = _mark_quote_sent_for_demo(db, quote=quote, actor=admin)
            elif scenario == "approved":
                quote = _mark_quote_sent_for_demo(db, quote=quote, actor=admin)
                public_approve_quote(quote_id=quote.id, t=str(quote.public_token), db=db)
                quote = _load_quote(db, quote.id)
            elif scenario == "change_requested":
                quote = _mark_quote_sent_for_demo(db, quote=quote, actor=admin)
                public_change_request_quote(
                    quote_id=quote.id,
                    payload=QuoteChangeRequestIn(message="Merci de me proposer un autre horaire."),
                    t=str(quote.public_token),
                    db=db,
                )
                quote = _load_quote(db, quote.id)
            elif scenario == "rejected":
                quote = _mark_quote_sent_for_demo(db, quote=quote, actor=admin)
                public_reject_quote(quote_id=quote.id, t=str(quote.public_token), db=db)
                quote = _load_quote(db, quote.id)
            elif scenario == "cancelled":
                quote = _mark_quote_sent_for_demo(db, quote=quote, actor=admin)
                cancel_quote(
                    quote_id=quote.id,
                    payload=QuoteCancelRequest(
                        notify_recipient=False,
                        notify_recipient_sms=False,
                    ),
                    db=db,
                    current_user=admin,
                )
                quote = _load_quote(db, quote.id)
            elif scenario == "reminder_due":
                quote = _mark_quote_sent_for_demo(db, quote=quote, actor=admin, expires_in=timedelta(hours=23))
                quote.reminder_sent_at = None
                db.add(quote)
                db.commit()
                db.refresh(quote)

            cases.append(
                SeededCase(
                    label=label,
                    category="quote",
                    status=str(quote.status or "").strip(),
                    intake_id=str(intake.id),
                    quote_id=str(quote.id),
                    quote_number=quote.quote_number,
                    admin_url=_admin_url(quote.id),
                    public_url=_public_url(quote),
                    notes=(
                        "Pret a tester dans le BO local."
                        if scenario not in {"reminder_due", "active_client"}
                        else (
                            "Expire volontairement dans moins de 24h."
                            if scenario == "reminder_due"
                            else "Contexte client existant / active_client."
                        )
                    ),
                )
            )

        print(json.dumps({"batch": batch, "cases": [asdict(item) for item in cases]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
