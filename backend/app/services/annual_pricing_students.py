"""Quote-bound identities, including prospects; never create clients or match by name.

Unconverted prospects retain their own identity and seasonal evidence in metadata.
Client evidence keeps using the existing FK-backed tables. Explicit conversion
links are the only bridge between the two, including during quote integration.
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.models.annual_pricing import AnnualFamilyReference, AnnualStudentEnrollment
from app.models.family import ClientFamilyLink
from app.models.quote import Prospect
from app.models.user import ClientKind, User, UserRole
from app.services.annual_enrollment import enrollment_context


def identity(db, identifier):
    if not identifier:
        return None
    try:
        identifier = UUID(str(identifier))
    except ValueError:
        return None
    return db.get(User, identifier) or db.get(Prospect, identifier)


def canonical_id(db, identifier):
    person = identity(db, identifier)
    if isinstance(person, Prospect) and person.linked_client_id:
        user = db.get(User, person.linked_client_id)
        if user and user.role == UserRole.CLIENT:
            return user.id
    return person.id if person else None


def is_child(person):
    return (person.meta or {}).get("prospect_type") == "child" if isinstance(person, Prospect) else person.client_kind == ClientKind.CHILD


def birth_date(person):
    if isinstance(person, User):
        return person.birth_date
    child = (person.meta or {}).get("child") or {}
    if not isinstance(child, dict):
        return None
    raw = child.get("birth_date") or child.get("date_of_birth")
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def label(person):
    return f"{person.first_name or ''} {person.last_name or ''}".strip()


def option(person):
    birth = birth_date(person)
    adult_age = bool(birth and (2026 - birth.year - ((9, 1) < (birth.month, birth.day))) >= 18)
    return {"id": str(person.id), "label": label(person),
            "kind": "PROSPECT" if isinstance(person, Prospect) else "CLIENT",
            "audiences": ["CHILD", "TEEN"] if is_child(person) and not adult_age else ["ADULT"]}


def family_members(db, student_id):
    """Traverse explicit family and conversion links (never contact details)."""
    students, guardians = {student_id}, set()
    while True:
        old = (set(students), set(guardians))
        for identifier in list(students):
            person = identity(db, identifier)
            if isinstance(person, Prospect):
                if person.linked_client_id:
                    students.add(person.linked_client_id)
                if person.parent_prospect_id:
                    guardians.add(person.parent_prospect_id)
            elif person:
                students.update(db.scalars(select(Prospect.id).where(Prospect.linked_client_id == identifier)))
        guardians.update(db.scalars(select(ClientFamilyLink.adult_user_id).where(ClientFamilyLink.child_user_id.in_(students))))
        for identifier in list(guardians):
            person = identity(db, identifier)
            if isinstance(person, Prospect) and person.linked_client_id:
                guardians.add(person.linked_client_id)
            elif isinstance(person, User):
                guardians.update(db.scalars(select(Prospect.id).where(Prospect.linked_client_id == identifier)))
        if guardians:
            students.update(db.scalars(select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id.in_(guardians))))
            students.update(db.scalars(select(Prospect.id).where(Prospect.parent_prospect_id.in_(guardians))))
        if old == (students, guardians):
            break
    return {canonical_id(db, i) for i in students if identity(db, i) and is_child(identity(db, i))}, guardians


def quote_students(db, quote):
    root = identity(db, quote.client_id or quote.prospect_id)
    if not root:
        return []
    # A quote addressed to a child is not a quote for an arbitrary sibling.
    if is_child(root):
        identifiers = {canonical_id(db, root.id)}
    else:
        identifiers = {canonical_id(db, root.id)}
        adult_ids = {root.id, canonical_id(db, root.id)}
        adult_ids.update(db.scalars(select(Prospect.id).where(Prospect.linked_client_id.in_(adult_ids))))
        identifiers.update(db.scalars(select(ClientFamilyLink.child_user_id).where(ClientFamilyLink.adult_user_id.in_(adult_ids))))
        identifiers.update(db.scalars(select(Prospect.id).where(Prospect.parent_prospect_id.in_(adult_ids))))
    people = {canonical_id(db, i): identity(db, canonical_id(db, i)) for i in identifiers if i}
    return sorted((p for p in people.values() if p and (isinstance(p, Prospect) or p.role == UserRole.CLIENT)), key=lambda p: (p.last_name or '', p.first_name or '', str(p.id)))


def student_enrollment(db, student_id, season):
    person = identity(db, student_id)
    cid = canonical_id(db, student_id)
    user = db.get(User, cid) if cid else None
    context = enrollment_context(db, cid, season) if user else {
        "status": "AUTO", "evidence": None, "history_found": False, "subscription_id": None}
    if user and db.get(AnnualStudentEnrollment, (cid, season)):
        return context
    prospects = [person] if isinstance(person, Prospect) else list(db.scalars(select(Prospect).where(Prospect.linked_client_id == cid)))
    saved = [(p.meta or {}).get("annual_enrollments", {}).get(season) for p in prospects]
    saved = [s for s in saved if s]
    if saved and any(s != saved[0] for s in saved):
        raise HTTPException(409, "Confirmations de réinscription contradictoires : vérifiez les fiches rattachées.")
    return {**context, **saved[0]} if saved else context


def save_enrollment(db, student_id, season, status, evidence):
    person = identity(db, student_id)
    if isinstance(person, Prospect) and not person.linked_client_id:
        person.meta = {**(person.meta or {}), "annual_enrollments": {
            **(person.meta or {}).get("annual_enrollments", {}), season: {"status": status, "evidence": evidence}}}
        person.updated_at = datetime.now(timezone.utc)
    else:
        cid = canonical_id(db, student_id)
        saved = db.get(AnnualStudentEnrollment, (cid, season)) or AnnualStudentEnrollment(student_id=cid, season=season)
        saved.status, saved.evidence = status, evidence
        db.add(saved)


def family_reference(db, guardian_id, season):
    guardian = identity(db, guardian_id)
    if isinstance(guardian, Prospect):
        saved = (guardian.meta or {}).get("annual_family_references", {}).get(season)
        return SimpleNamespace(child_id=UUID(saved["child_id"]), evidence=saved.get("evidence")) if saved else None
    if not guardian:
        return None
    refs = [db.get(AnnualFamilyReference, (guardian_id, season))]
    refs.extend(family_reference(db, p.id, season) for p in db.scalars(select(Prospect).where(Prospect.linked_client_id == guardian_id)))
    refs = [r for r in refs if r]
    if refs and any(canonical_id(db, r.child_id) != canonical_id(db, refs[0].child_id) for r in refs):
        raise HTTPException(409, "Références familiales contradictoires entre les fiches client et prospect. Vérifiez les rattachements.")
    return refs[0] if refs else None


def save_family_reference(db, guardian_id, child_id, season, evidence):
    guardian = identity(db, guardian_id)
    # An unconverted reference cannot enter the client-only FK table. Store it
    # on the explicit parent prospect; require one rather than inventing a link.
    if isinstance(guardian, User) and isinstance(identity(db, child_id), Prospect):
        parents = list(db.scalars(select(Prospect).where(Prospect.linked_client_id == guardian_id)))
        if not parents:
            raise HTTPException(409, "Rattachez le responsable prospect à sa fiche client avant de confirmer cette référence familiale.")
        for parent in parents:
            save_family_reference(db, parent.id, child_id, season, evidence)
        return
    if isinstance(guardian, Prospect):
        guardian.meta = {**(guardian.meta or {}), "annual_family_references": {
            **(guardian.meta or {}).get("annual_family_references", {}), season: {"child_id": str(child_id), "evidence": evidence}}}
        guardian.updated_at = datetime.now(timezone.utc)
    else:
        ref = db.get(AnnualFamilyReference, (guardian_id, season)) or AnnualFamilyReference(guardian_id=guardian_id, season=season)
        ref.child_id, ref.evidence = canonical_id(db, child_id), evidence
        db.add(ref)


def review_client_id(db, review):
    identifier = review.get("student_id")
    if review.get("student_kind", "CLIENT") == "PROSPECT":
        prospect = db.get(Prospect, UUID(identifier)) if identifier else None
        return prospect.linked_client_id if prospect else None
    return UUID(identifier) if identifier else None


def review_prospect_for_transformation(db, quote):
    review = (getattr(quote, "meta", None) or {}).get("annual_pricing_review") or {}
    if review.get("student_kind") != "PROSPECT":
        return None
    person = db.get(Prospect, UUID(review["student_id"]))
    if not person or canonical_id(db, person.id) not in {s.id for s in quote_students(db, quote)}:
        raise HTTPException(409, "Le prospect vérifié n'est plus rattaché à ce devis. Vérifiez l'élève avant transformation.")
    return person


def lock_family(db, identifiers):
    # All callers acquire locks in the same table/UUID order. Reload metadata
    # after waiting so concurrent confirmations cannot overwrite each other.
    for model in (User, Prospect):
        db.scalars(select(model).where(model.id.in_(identifiers)).order_by(model.id)
                   .with_for_update().execution_options(populate_existing=True)).all()


def identity_evidence(db, student, guardians):
    return {"id": str(student.id), "kind": option(student)["kind"], "birth_date": str(birth_date(student)),
            "child": is_child(student), "canonical_id": str(canonical_id(db, student.id)),
            "guardians": sorted(str(i) for i in guardians)}
