from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from hashlib import sha1
from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.client_import_reference import ClientImportReference
from app.models.family import ClientFamilyLink
from app.models.user import ClientKind, ClientStatus, User, UserRole
from app.services.client_email import normalize_contact_email
from app.services.client_password_email import generate_temporary_password
from app.services.security import hash_password

SOURCE_SYSTEM = "MYMUSICSTAFF"
EXTERNAL_KIND_STUDENT = "STUDENT"
EXTERNAL_KIND_PARENT = "PARENT_CONTACT"
DEFAULT_COUNTRY = "FR"
DEFAULT_TIMEZONE = "Europe/Paris"
DEFAULT_CURRENCY = "EUR"
NO_EMAIL_DOMAIN = "no-email.local"
REQUIRED_HEADERS = {
    "Nom de famille",
    "Prénom",
    "ID étudiant My Music Staff",
}
PARENT_CONTACT_SLOTS = range(1, 5)
POSTAL_CODE_RE = re.compile(r"\b(\d{5})\b")
COUNTRY_TRAILER_RE = re.compile(r"(?:,?\s*)(FRANCE|FR)\s*$", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class ParsedAddress:
    address_line: str | None
    postal_code: str | None
    city: str | None
    country_code: str = DEFAULT_COUNTRY


@dataclass(slots=True)
class ParentContactRow:
    external_id: str
    family_external_id: str | None
    slot_index: int
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    address: ParsedAddress
    sms_opt_in: bool
    source_note: str | None

    @property
    def display_name(self) -> str:
        return _display_name(self.first_name, self.last_name)


@dataclass(slots=True)
class StudentRow:
    row_number: int
    external_id: str
    family_external_id: str | None
    first_name: str
    last_name: str
    client_kind: ClientKind
    email: str | None
    phone: str | None
    address: ParsedAddress
    birth_date: date | None
    source_status: str | None
    start_date: date | None
    inactive_date: date | None
    source_note: str | None
    sms_opt_in: bool
    parents: list[ParentContactRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return _display_name(self.first_name, self.last_name)


@dataclass(slots=True)
class UserPayload:
    external_kind: str
    external_id: str
    family_external_id: str | None
    client_kind: ClientKind
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    address: ParsedAddress
    birth_date: date | None
    sms_opt_in: bool
    source_note: str | None
    source_status: str | None

    @property
    def display_name(self) -> str:
        return _display_name(self.first_name, self.last_name)


@dataclass(slots=True)
class EntityPreview:
    external_kind: str
    external_id: str
    family_external_id: str | None
    client_kind: ClientKind
    display_name: str
    action: Literal["CREATE", "UPDATE"]
    warning_messages: list[str]


@dataclass(slots=True)
class ResolvedUser:
    user: User
    action: Literal["CREATE", "UPDATE"]
    warning_messages: list[str]


def preview_mymusicstaff_import(csv_bytes: bytes, db: Session, file_name: str | None = None) -> dict[str, object]:
    rows = _parse_rows(csv_bytes)
    student_previews: list[EntityPreview] = []
    parent_previews: list[EntityPreview] = []
    preview_warnings = _collect_row_warnings(rows)

    for row in rows:
        student_payload = _student_payload_from_row(row)
        student_previews.append(_preview_entity(db, student_payload))
        for parent in row.parents:
            parent_previews.append(_preview_entity(db, _parent_payload_from_row(parent)))

    parent_by_external_id = _dedupe_previews(parent_previews)
    student_by_external_id = _dedupe_previews(student_previews)

    would_create_clients = sum(1 for item in [*parent_by_external_id.values(), *student_by_external_id.values()] if item.action == "CREATE")
    would_update_clients = sum(1 for item in [*parent_by_external_id.values(), *student_by_external_id.values()] if item.action == "UPDATE")

    would_create_family_links = 0
    for row in rows:
        if row.client_kind != ClientKind.CHILD:
            continue
        student_preview = student_by_external_id[row.external_id]
        for parent in row.parents:
            parent_preview = parent_by_external_id[parent.external_id]
            existing_link = False
            if student_preview.action == "UPDATE" and parent_preview.action == "UPDATE":
                student_user = _find_existing_user_for_preview(
                    db,
                    external_kind=EXTERNAL_KIND_STUDENT,
                    external_id=row.external_id,
                    family_external_id=row.family_external_id,
                    client_kind=row.client_kind,
                    email=row.email,
                    first_name=row.first_name,
                    last_name=row.last_name,
                )
                parent_user = _find_existing_user_for_preview(
                    db,
                    external_kind=EXTERNAL_KIND_PARENT,
                    external_id=parent.external_id,
                    family_external_id=parent.family_external_id,
                    client_kind=ClientKind.ADULT,
                    email=parent.email,
                    first_name=parent.first_name,
                    last_name=parent.last_name,
                )
                if student_user is not None and parent_user is not None:
                    existing_link = _family_link_exists(db, adult_user_id=parent_user.id, child_user_id=student_user.id)
            if not existing_link:
                would_create_family_links += 1

    sample_rows = []
    for row in rows[:20]:
        sample_rows.append(
            {
                "student_external_id": row.external_id,
                "family_external_id": row.family_external_id,
                "display_name": row.display_name,
                "client_kind": row.client_kind.value,
                "action": student_by_external_id[row.external_id].action,
                "parent_contacts_count": len(row.parents),
                "warning_messages": list(dict.fromkeys(row.warnings + student_by_external_id[row.external_id].warning_messages)),
            }
        )

    all_warnings = list(dict.fromkeys(preview_warnings + _flatten_warning_messages(student_by_external_id.values()) + _flatten_warning_messages(parent_by_external_id.values())))

    return {
        "source_system": SOURCE_SYSTEM,
        "file_name": file_name,
        "rows_total": len(rows),
        "students_detected": len(student_by_external_id),
        "adult_students_detected": sum(1 for row in rows if row.client_kind == ClientKind.ADULT),
        "child_students_detected": sum(1 for row in rows if row.client_kind == ClientKind.CHILD),
        "parent_contacts_detected": len(parent_by_external_id),
        "families_detected": len({row.family_external_id for row in rows if row.family_external_id}),
        "would_create_clients": would_create_clients,
        "would_update_clients": would_update_clients,
        "would_create_family_links": would_create_family_links,
        "warnings": all_warnings[:100],
        "sample_rows": sample_rows,
    }


def execute_mymusicstaff_import(csv_bytes: bytes, db: Session, file_name: str | None = None) -> dict[str, object]:
    rows = _parse_rows(csv_bytes)
    results: list[str] = []
    parents_created = 0
    parents_updated = 0
    students_created = 0
    students_updated = 0
    family_links_created = 0
    family_links_updated = 0

    user_cache: dict[tuple[str, str], ResolvedUser] = {}

    for row in rows:
        student_payload = _student_payload_from_row(row)
        student_resolved = _resolve_or_create_user(db, student_payload, user_cache)
        if student_resolved.action == "CREATE":
            students_created += 1
        else:
            students_updated += 1
        results.extend(student_resolved.warning_messages)

        if row.client_kind != ClientKind.CHILD:
            continue

        billing_parent_external_id = row.parents[0].external_id if row.parents else None
        for parent in row.parents:
            parent_resolved = _resolve_or_create_user(db, _parent_payload_from_row(parent), user_cache)
            if parent_resolved.action == "CREATE":
                parents_created += 1
            else:
                parents_updated += 1
            results.extend(parent_resolved.warning_messages)
            link_action = _ensure_family_link(
                db,
                adult_user=parent_resolved.user,
                child_user=student_resolved.user,
                relationship_label="Parent",
                is_billing_recipient=parent.external_id == billing_parent_external_id,
            )
            if link_action == "CREATE":
                family_links_created += 1
            elif link_action == "UPDATE":
                family_links_updated += 1

    db.commit()

    distinct_warnings = list(dict.fromkeys(_collect_row_warnings(rows) + results))
    return {
        "source_system": SOURCE_SYSTEM,
        "file_name": file_name,
        "rows_total": len(rows),
        "processed_students": len(rows),
        "parents_created": parents_created,
        "parents_updated": parents_updated,
        "students_created": students_created,
        "students_updated": students_updated,
        "family_links_created": family_links_created,
        "family_links_updated": family_links_updated,
        "warnings": distinct_warnings[:100],
        "summary": (
            f"Import MyMusicStaff termine: {students_created} eleve(s) cree(s), "
            f"{students_updated} eleve(s) mis a jour, {parents_created} parent(s) cree(s), "
            f"{parents_updated} parent(s) mis a jour."
        ),
    }


def _parse_rows(csv_bytes: bytes) -> list[StudentRow]:
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Le CSV doit etre encode en UTF-8.") from exc

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    headers = set(reader.fieldnames or [])
    missing = sorted(REQUIRED_HEADERS - headers)
    if missing:
        raise ValueError(f"Colonnes CSV manquantes: {', '.join(missing)}")

    rows: list[StudentRow] = []
    seen_student_ids: set[str] = set()

    for row_number, row in enumerate(reader, start=2):
        external_id = _normalize_optional(row.get("ID étudiant My Music Staff"))
        first_name = _normalize_required_csv(row.get("Prénom"), "Prénom", row_number)
        last_name = _normalize_required_csv(row.get("Nom de famille"), "Nom de famille", row_number)
        if not external_id:
            raise ValueError(f"Ligne {row_number}: ID étudiant My Music Staff manquant.")
        if external_id in seen_student_ids:
            raise ValueError(f"Ligne {row_number}: ID étudiant duplique ({external_id}).")
        seen_student_ids.add(external_id)

        family_external_id = _normalize_optional(row.get("ID de la famille My Music Staff"))
        client_kind = ClientKind.ADULT if _normalize_optional(row.get("Étudiant adulte")) == "Adulte" else ClientKind.CHILD
        student = StudentRow(
            row_number=row_number,
            external_id=external_id,
            family_external_id=family_external_id,
            first_name=first_name,
            last_name=last_name,
            client_kind=client_kind,
            email=_normalize_email(row.get("Courriel")),
            phone=_normalize_phone(row.get("Téléphone portable")),
            address=_parse_address(row.get("Adresse")),
            birth_date=_parse_date(row.get("Anniversaire")),
            source_status=_normalize_optional(row.get("Statut")),
            start_date=_parse_date(row.get("Date de début")),
            inactive_date=_parse_date(row.get("Date d'inactivité")),
            source_note=_normalize_optional(row.get("Note")),
            sms_opt_in=_parse_yes_no(row.get("Envoi de SMS autorisé")),
            parents=[],
            warnings=[],
        )
        if not student.email and client_kind == ClientKind.ADULT:
            student.warnings.append(f"{student.display_name}: email adulte absent, un email technique sera cree.")

        for slot_index in PARENT_CONTACT_SLOTS:
            parent = _parse_parent_contact(row, slot_index=slot_index, row_number=row_number, family_external_id=family_external_id, student_external_id=external_id)
            if parent is not None:
                student.parents.append(parent)

        if client_kind == ClientKind.CHILD and not student.parents:
            student.warnings.append(f"{student.display_name}: aucun parent contact exploitable dans le CSV.")

        rows.append(student)

    if not rows:
        raise ValueError("Le fichier CSV ne contient aucune ligne exploitable.")

    return rows


def _parse_parent_contact(
    row: dict[str, str | None],
    *,
    slot_index: int,
    row_number: int,
    family_external_id: str | None,
    student_external_id: str,
) -> ParentContactRow | None:
    last_name = _normalize_optional(row.get(f"Nom de famille du parent contact {slot_index}"))
    first_name = _normalize_optional(row.get(f"Prénom du parent contact {slot_index}"))
    email = _normalize_email(row.get(f"Contact du parent {slot_index} courriel"))
    address = _parse_address(row.get(f"Adresse de contact du parent {slot_index}"))
    phone = _normalize_phone(
        row.get(f"Contact parent {slot_index} téléphone portable")
        or row.get(f"Contact parent {slot_index} téléphone domicile")
        or row.get(f"Contact parent {slot_index} téléphone professionnel")
    )
    source_note = _normalize_optional(row.get(f"Note de contact du parent {slot_index}"))
    sms_opt_in = _parse_yes_no(
        row.get(f"Contact parent {slot_index} SMS autorisé")
        or row.get(f"Contact parent {slot_index} SMS à domicile autorisé")
        or row.get(f"Contact parent {slot_index} SMS professionnel autorisé")
    )

    if not any([first_name, last_name, email, phone, address.address_line]):
        return None

    if not first_name:
        first_name = f"Parent {slot_index}"
    if not last_name:
        last_name = _normalize_optional(row.get("Nom de famille")) or f"Famille {student_external_id}"

    external_id = family_external_id and f"{family_external_id}:parent_contact:{slot_index}" or f"{student_external_id}:parent_contact:{slot_index}"
    return ParentContactRow(
        external_id=external_id,
        family_external_id=family_external_id,
        slot_index=slot_index,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        address=address,
        sms_opt_in=sms_opt_in,
        source_note=source_note,
    )


def _preview_entity(db: Session, payload: UserPayload) -> EntityPreview:
    warnings: list[str] = []
    action: Literal["CREATE", "UPDATE"] = "CREATE"
    existing = _find_existing_user_for_preview(
        db,
        external_kind=payload.external_kind,
        external_id=payload.external_id,
        family_external_id=payload.family_external_id,
        client_kind=payload.client_kind,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    if existing is not None:
        action = "UPDATE"
    elif payload.email:
        desired_email = normalize_contact_email(payload.email)
        collision = db.scalar(
            select(User.id)
            .where(or_(User.email == desired_email, User.contact_email == desired_email))
            .limit(1)
        )
        if collision is not None:
            warnings.append(
                f"{payload.display_name}: email {payload.email} deja utilise, un email technique sera conserve a l'import."
            )

    return EntityPreview(
        external_kind=payload.external_kind,
        external_id=payload.external_id,
        family_external_id=payload.family_external_id,
        client_kind=payload.client_kind,
        display_name=payload.display_name,
        action=action,
        warning_messages=warnings,
    )


def _find_existing_user_for_preview(
    db: Session,
    *,
    external_kind: str,
    external_id: str,
    family_external_id: str | None,
    client_kind: ClientKind,
    email: str | None,
    first_name: str,
    last_name: str,
) -> User | None:
    reference = db.scalar(
        select(ClientImportReference)
        .where(
            ClientImportReference.source_system == SOURCE_SYSTEM,
            ClientImportReference.external_kind == external_kind,
            ClientImportReference.external_id == external_id,
        )
        .limit(1)
    )
    if reference is not None:
        user = db.scalar(select(User).where(User.id == reference.user_id, User.role == UserRole.CLIENT).limit(1))
        if user is not None:
            return user

    return _find_safe_existing_user_match(
        db,
        client_kind=client_kind,
        email=email,
        first_name=first_name,
        last_name=last_name,
    )


def _find_safe_existing_user_match(
    db: Session,
    *,
    client_kind: ClientKind,
    email: str | None,
    first_name: str,
    last_name: str,
) -> User | None:
    normalized_email = normalize_contact_email(email)
    if not normalized_email:
        return None
    candidates = db.scalars(
        select(User).where(
            User.role == UserRole.CLIENT,
            User.client_kind == client_kind,
            or_(User.email == normalized_email, User.contact_email == normalized_email),
        )
    ).all()
    normalized_first = _normalize_name_for_match(first_name)
    normalized_last = _normalize_name_for_match(last_name)
    exact = [
        user
        for user in candidates
        if _normalize_name_for_match(user.first_name) == normalized_first
        and _normalize_name_for_match(user.last_name) == normalized_last
    ]
    if len(exact) == 1:
        return exact[0]
    return None


def _resolve_or_create_user(db: Session, payload: UserPayload, cache: dict[tuple[str, str], ResolvedUser]) -> ResolvedUser:
    cache_key = (payload.external_kind, payload.external_id)
    if cache_key in cache:
        return cache[cache_key]

    warnings: list[str] = []
    reference = db.scalar(
        select(ClientImportReference)
        .where(
            ClientImportReference.source_system == SOURCE_SYSTEM,
            ClientImportReference.external_kind == payload.external_kind,
            ClientImportReference.external_id == payload.external_id,
        )
        .with_for_update()
    )
    user: User | None = None
    action: Literal["CREATE", "UPDATE"] = "CREATE"

    if reference is not None:
        user = db.scalar(select(User).where(User.id == reference.user_id, User.role == UserRole.CLIENT).with_for_update())
        if user is not None:
            action = "UPDATE"

    if user is None:
        safe_match = _find_safe_existing_user_match(
            db,
            client_kind=payload.client_kind,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
        if safe_match is not None:
            user = safe_match
            action = "UPDATE"

    if user is None:
        desired_email = normalize_contact_email(payload.email)
        contact_email = desired_email
        if desired_email and db.scalar(select(User.id).where(User.email == desired_email).limit(1)) is not None:
            warnings.append(
                f"{payload.display_name}: email {desired_email} deja utilise, creation avec email technique."
            )
            desired_email = None
        user = User(
            email=desired_email or _synthetic_email(payload.external_kind, payload.external_id),
            contact_email=contact_email,
            hashed_password=hash_password(generate_temporary_password()),
            role=UserRole.CLIENT,
            client_kind=payload.client_kind,
            client_status=ClientStatus.INACTIVE,
            is_active=False,
            address_country=payload.address.country_code,
            residence_country=payload.address.country_code,
            preferred_currency=DEFAULT_CURRENCY,
            timezone=DEFAULT_TIMEZONE,
            portal_contact_visible=True,
            email_opt_in=bool(contact_email),
            sms_opt_in=payload.sms_opt_in,
            lesson_reminder_email_opt_in=bool(contact_email),
            lesson_reminder_sms_opt_in=payload.sms_opt_in,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(user)
        db.flush()
    else:
        action = "UPDATE"

    _merge_user_from_payload(user, payload, created=action == "CREATE")
    user.updated_at = _utcnow()
    db.add(user)
    db.flush()

    if reference is None:
        reference = ClientImportReference(
            user_id=user.id,
            source_system=SOURCE_SYSTEM,
            external_kind=payload.external_kind,
            external_id=payload.external_id,
            external_family_id=payload.family_external_id,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(reference)
    else:
        reference.user_id = user.id
        reference.external_family_id = payload.family_external_id
        reference.updated_at = _utcnow()
        db.add(reference)
    db.flush()

    resolved = ResolvedUser(user=user, action=action, warning_messages=warnings)
    cache[cache_key] = resolved
    return resolved


def _merge_user_from_payload(user: User, payload: UserPayload, *, created: bool) -> None:
    user.client_kind = payload.client_kind
    user.first_name = _pick_text_value(user.first_name, payload.first_name, created=created)
    user.last_name = _pick_text_value(user.last_name, payload.last_name, created=created)
    user.address_line = _pick_text_value(user.address_line, payload.address.address_line, created=created)
    user.postal_code = _pick_text_value(user.postal_code, payload.address.postal_code, created=created)
    user.city = _pick_text_value(user.city, payload.address.city, created=created)
    user.address_country = payload.address.country_code or user.address_country or DEFAULT_COUNTRY
    user.residence_country = payload.address.country_code or user.residence_country or DEFAULT_COUNTRY
    user.phone = _pick_text_value(user.phone, payload.phone, created=created)
    user.mobile_phone_1 = _pick_text_value(user.mobile_phone_1, payload.phone, created=created)
    user.birth_date = payload.birth_date or user.birth_date
    normalized_email = normalize_contact_email(payload.email)
    user.contact_email = _pick_text_value(user.contact_email, normalized_email, created=created)
    if created and normalized_email:
        user.email_opt_in = True
        user.lesson_reminder_email_opt_in = True
    if created:
        user.sms_opt_in = payload.sms_opt_in
        user.lesson_reminder_sms_opt_in = payload.sms_opt_in
    if created and payload.source_note:
        user.important_info = _truncate(payload.source_note, 1000)


def _ensure_family_link(
    db: Session,
    *,
    adult_user: User,
    child_user: User,
    relationship_label: str | None,
    is_billing_recipient: bool,
) -> Literal["CREATE", "UPDATE", "UNCHANGED"]:
    existing = db.scalar(
        select(ClientFamilyLink)
        .where(
            ClientFamilyLink.adult_user_id == adult_user.id,
            ClientFamilyLink.child_user_id == child_user.id,
        )
        .with_for_update()
    )
    now = _utcnow()
    if existing is None:
        existing = ClientFamilyLink(
            adult_user_id=adult_user.id,
            child_user_id=child_user.id,
            relationship_label=relationship_label,
            is_billing_recipient=False,
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
        db.flush()
        action: Literal["CREATE", "UPDATE", "UNCHANGED"] = "CREATE"
    else:
        action = "UNCHANGED"
        if relationship_label and not existing.relationship_label:
            existing.relationship_label = relationship_label
            action = "UPDATE"

    if is_billing_recipient:
        db.query(ClientFamilyLink).filter(ClientFamilyLink.child_user_id == child_user.id).update(
            {"is_billing_recipient": False, "updated_at": now},
            synchronize_session=False,
        )
        existing.is_billing_recipient = True
        action = "UPDATE" if action != "CREATE" else action
    existing.updated_at = now
    db.add(existing)
    db.flush()
    return action


def _family_link_exists(db: Session, *, adult_user_id: UUID, child_user_id: UUID) -> bool:
    return (
        db.scalar(
            select(ClientFamilyLink.id)
            .where(
                ClientFamilyLink.adult_user_id == adult_user_id,
                ClientFamilyLink.child_user_id == child_user_id,
            )
            .limit(1)
        )
        is not None
    )


def _student_payload_from_row(row: StudentRow) -> UserPayload:
    return UserPayload(
        external_kind=EXTERNAL_KIND_STUDENT,
        external_id=row.external_id,
        family_external_id=row.family_external_id,
        client_kind=row.client_kind,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
        phone=row.phone,
        address=row.address,
        birth_date=row.birth_date,
        sms_opt_in=row.sms_opt_in,
        source_note=row.source_note,
        source_status=row.source_status,
    )


def _parent_payload_from_row(parent: ParentContactRow) -> UserPayload:
    return UserPayload(
        external_kind=EXTERNAL_KIND_PARENT,
        external_id=parent.external_id,
        family_external_id=parent.family_external_id,
        client_kind=ClientKind.ADULT,
        first_name=parent.first_name,
        last_name=parent.last_name,
        email=parent.email,
        phone=parent.phone,
        address=parent.address,
        birth_date=None,
        sms_opt_in=parent.sms_opt_in,
        source_note=parent.source_note,
        source_status=None,
    )


def _dedupe_previews(previews: list[EntityPreview]) -> dict[str, EntityPreview]:
    deduped: dict[str, EntityPreview] = {}
    for preview in previews:
        if preview.external_id not in deduped:
            deduped[preview.external_id] = preview
            continue
        merged_warnings = list(dict.fromkeys(deduped[preview.external_id].warning_messages + preview.warning_messages))
        if deduped[preview.external_id].action == "CREATE" and preview.action == "UPDATE":
            deduped[preview.external_id].action = "UPDATE"
        deduped[preview.external_id].warning_messages = merged_warnings
    return deduped


def _collect_row_warnings(rows: list[StudentRow]) -> list[str]:
    warnings: list[str] = []
    for row in rows:
        warnings.extend(row.warnings)
    return list(dict.fromkeys(warnings))


def _flatten_warning_messages(items: list[EntityPreview] | dict_values_proxy) -> list[str]:
    flattened: list[str] = []
    for item in items:
        flattened.extend(item.warning_messages)
    return flattened


class dict_values_proxy:  # pragma: no cover - typing helper only
    def __iter__(self): ...


def _normalize_required_csv(value: str | None, label: str, row_number: int) -> str:
    normalized = _normalize_optional(value)
    if normalized:
        return normalized
    raise ValueError(f"Ligne {row_number}: {label} manquant.")


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = SPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()
    return normalized or None


def _normalize_email(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    if not normalized:
        return None
    return normalized.lower()


def _normalize_phone(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    if not normalized:
        return None
    return normalized


def _parse_yes_no(value: str | None) -> bool:
    normalized = (_normalize_optional(value) or "").upper()
    return normalized in {"Y", "YES", "O", "OUI", "TRUE", "1"}


def _parse_date(value: str | None) -> date | None:
    normalized = _normalize_optional(value)
    if not normalized:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def _parse_address(value: str | None) -> ParsedAddress:
    normalized = _normalize_optional(value)
    if not normalized:
        return ParsedAddress(address_line=None, postal_code=None, city=None, country_code=DEFAULT_COUNTRY)

    country_code = DEFAULT_COUNTRY
    without_country = COUNTRY_TRAILER_RE.sub("", normalized).strip(" ,;-")
    postal_match = POSTAL_CODE_RE.search(without_country)
    if postal_match is None:
        return ParsedAddress(address_line=without_country[:255], postal_code=None, city=None, country_code=country_code)

    postal_code = postal_match.group(1)
    before = without_country[: postal_match.start()].strip(" ,;-")
    after = without_country[postal_match.end() :].strip(" ,;-")
    address_line = before or without_country
    city = after or None

    if not city and "," in before:
        segments = [segment.strip(" ,;-") for segment in before.split(",") if segment.strip(" ,;-")]
        if len(segments) >= 2 and _looks_like_city_segment(segments[-1]):
            city = segments[-1]
            address_line = ", ".join(segments[:-1]) or before
    elif not city:
        merged = re.match(r"^(.*?)([A-Za-zÀ-ÿ' -]{2,})$", before)
        if merged is not None and _looks_like_city_segment(merged.group(2)):
            city = merged.group(2).strip(" ,;-")
            address_line = merged.group(1).strip(" ,;-") or before

    return ParsedAddress(
        address_line=_truncate(address_line, 255),
        postal_code=postal_code,
        city=_truncate(city, 120) if city else None,
        country_code=country_code,
    )


def _looks_like_city_segment(value: str | None) -> bool:
    normalized = _normalize_optional(value)
    if not normalized:
        return False
    if any(char.isdigit() for char in normalized):
        return False
    return len(normalized) <= 40


def _synthetic_email(external_kind: str, external_id: str) -> str:
    digest = sha1(f"{external_kind}:{external_id}".encode("utf-8")).hexdigest()[:16]
    prefix = "parent" if external_kind == EXTERNAL_KIND_PARENT else "student"
    return f"mms-{prefix}-{digest}@{NO_EMAIL_DOMAIN}"


def _display_name(first_name: str | None, last_name: str | None) -> str:
    return " ".join(part for part in [first_name, last_name] if part).strip() or "Sans nom"


def _normalize_name_for_match(value: str | None) -> str:
    return (_normalize_optional(value) or "").casefold()


def _pick_text_value(existing: str | None, incoming: str | None, *, created: bool) -> str | None:
    normalized_incoming = _normalize_optional(incoming)
    if created:
        return normalized_incoming
    if not _normalize_optional(existing) and normalized_incoming:
        return normalized_incoming
    return existing


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
