"""Reuse reviewed course decisions without re-evaluating family or booking chronology."""
from dataclasses import replace
from decimal import Decimal
from datetime import datetime

from fastapi import HTTPException
from app.services.client_pricing import PricingComponent, PricingChannel, compute_contract_price


def decorate_contract_price(price, decision):
    if not decision:
        return price
    return replace(price, base_amount_ttc=Decimal(decision["base"]), version=decision["version"],
        components=tuple(PricingComponent(c["code"], c["label"], Decimal(c["amount_ttc"])) for c in decision["pricing"]["components"]))


def contract_price_for_session(subscription, session, *, now):
    terms = getattr(subscription, "annual_pricing_terms", None) or []
    candidates = [t for t in terms if t["activity_id"] == str(session.course_type_id)]
    if not candidates:
        return None
    duration = int((session.end_at_utc - session.start_at_utc).total_seconds() / 60)
    matches = [t for t in candidates if t["location_id"] == str(session.location_id)
        and t["duration_minutes"] == duration
        and str(session.id) in t.get("session_ids", [])]
    if len(matches) != 1:
        raise HTTPException(409, "Ce créneau ne correspond pas à un cours contractuel unique. Utilisez Déplacer ou faites valider un avenant ; aucune remise n'est attribuée par ordre de réservation.")
    decision = matches[0]
    p = decision["pricing"]
    return decorate_contract_price(compute_contract_price(channel=PricingChannel.QUOTE,
        amount_excl_vat=p["amount_excl_vat"], vat_rate=p["vat_rate"], vat_amount=p["vat_amount"],
        total_incl_vat=p["total_incl_vat"], currency=p["currency"], source=p["source"],
        version=decision["version"], calculated_at=now), decision)


def bind_contract_course(subscription, decision, sessions):
    if not decision or not subscription:
        return
    if any(str(s.course_type_id) != decision["activity_id"] or str(s.location_id) != decision["location_id"]
           or int((s.end_at_utc - s.start_at_utc).total_seconds() / 60) != decision["duration_minutes"] for s in sessions):
        raise HTTPException(409, "Activité, lieu ou durée différents du devis tarifé : un avenant est nécessaire.")
    if len(sessions) != int(Decimal(decision["quantity"])):
        raise HTTPException(409, "Le nombre de séances diffère de la décision tarifaire du devis.")
    terms = list(getattr(subscription, "annual_pricing_terms", None) or [])
    if any(t["course_key"] == decision["course_key"] for t in terms):
        raise HTTPException(409, "Ce cours contractuel a déjà été intégré.")
    terms.append({**decision, "series_ids": sorted({str(s.recurrence_group_id) for s in sessions if s.recurrence_group_id}),
                  "session_ids": [str(s.id) for s in sessions]})
    subscription.annual_pricing_terms = terms
