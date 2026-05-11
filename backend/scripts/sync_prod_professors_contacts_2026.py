from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.catalog import Professor
from app.models.professor_access import ProfessorPermission
from app.models.user import User, UserRole
from app.services.professor_permissions import DEFAULT_PROFESSOR_PERMISSIONS, ensure_permissions_row
from app.services.security import hash_password

SCRIPT_PREFIX = "SYNC_PROFESSORS_CONTACTS_2026"


@dataclass(frozen=True)
class ContactRow:
    initials: str | None
    full_name: str
    email: str
    address_line: str | None
    phone: str | None
    status: str
    role: str
    full_access: str
    remarks: str | None


CONTACTS: tuple[ContactRow, ...] = (
    ContactRow("AF", "Ana Gabriela Fernandez", "anafernandez174@yahoo.es", None, "+33 6 51 84 88 83", "Actif", "Teacher", "Non", "-"),
    ContactRow(None, "Ariane DEMANGE", "arianececiled@yahoo.fr", "37 rue Rodier 75009, Paris", "06 73 73 14 74", "Actif", "Teacher", "Non", "-"),
    ContactRow("CM", "Chiharu Matsuura", "y.h.music.18.elmo@gmail.com", None, "0768459003", "Actif", "Teacher", "Non", "-"),
    ContactRow(None, "Estela Oliviero", "nomys2015@gmail.com", "10 rue Michelet Bois le roi 77590", "0641387046", "Actif", "Teacher", "Non", "-"),
    ContactRow("FM", "Fernanda MACHADO", "Fernachado.violinista@gmail.com", "24 Rue du Buisson Saint-Louis 75010", "07 62 39 84 55", "Actif", "Teacher", "Non", "-"),
    ContactRow("FM", "Florean Mélaine", "florean.melaine@outlook.com", None, "07 89 41 41 90", "Actif", "Teacher", "Non", "-"),
    ContactRow(None, "Gayane Nersisyan", "gay_jan93@yahoo.com", "57 Boulevard Jourdan 75014 PARIS", "07 63 91 78 07", "Actif", "Teacher", "Non", "-"),
    ContactRow("HS", "Haluna Sato Tellier", "halunasatotellier@gmail.com", "6 rue Lakanal, 93500 Pantin", "06 98 36 54 30", "Actif", "Teacher", "Non", "-"),
    ContactRow("MS", "Marinella Sidy", "marinellasidy@gmail.com", "5 square voltaire Cachan 94230", "07 70 27 72 08", "Actif", "Teacher", "Non", "-"),
    ContactRow(None, "Mi-Young LEE", "miyoung.lee@piano-academie.com", None, "0635662012", "Actif", "Teacher", "Oui", "-"),
    ContactRow("MG", "Myriam Gueye", "myriamgueye10@gmail.com", "119 boulevard brune 75014", "0684582289", "Actif", "Teacher", "Non", "-"),
    ContactRow(None, "Neda Malisic", "malisicneda@yahoo.com", "11 VILLA COMPOINT 75017 PARIS", "06 13 57 50 95", "Actif", "Teacher", "Non", "-"),
    ContactRow("PC", "PAISHAO CHENG", "julia.841023@gmail.com", None, None, "Actif", "Teacher", "Non", "-"),
    ContactRow("RG", "Rosana Guirado Pifero", "rosanaguirado@gmail.com", None, None, "Actif", "Teacher", "Non", "-"),
    ContactRow("RG", "Rudy GATTI", "rudygatti2001@gmail.com", "94 avenue du belvedere 93310 Pres Saint Gervais", "0649002991", "Actif", "Teacher", "Non", "-"),
    ContactRow(None, "Rym MEDIOUNI", "rymmediouni@gmail.com", None, "0620882728", "Actif", "Teacher", "Non", "-"),
    ContactRow("SA", "Service ADMINISTRATION", "administration@piano-academie.com", "30 rue Vineuse 75116", "0649002991", "Actif", "Teacher", "Oui", "-"),
    ContactRow(None, "Rym MEDIOUNI", "rymmediouni@gmail.com", None, "0620882728", "Actif", "Teacher", "Non", "-"),
    ContactRow("SH", "Sung Bin Hong", "rosehongv@gmail.com", None, "+33 6 51 71 37 36", "Actif", "Teacher", "Non", "-"),
    ContactRow("YR", "YouJin Roh", "ryoujin0912@yahoo.com", None, "07 68 55 97 49", "Actif", "Teacher", "Non", "-"),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: object | None) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"nan", "-", "none"}:
        return None
    return " ".join(raw.split())


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _normalized_email(value: object | None) -> str:
    raw = _clean(value)
    if not raw:
        raise ValueError("Chaque professeur doit avoir un email pour une synchronisation fiable.")
    return raw.lower()


def _normalized_label(value: object | None) -> str:
    raw = _clean(value) or ""
    return _strip_accents(raw).casefold()


def _split_full_name(full_name: str) -> tuple[str, str]:
    parts = (_clean(full_name) or "").split()
    if len(parts) < 2:
        return full_name.strip(), ""
    return " ".join(parts[:-1]), parts[-1]


def _is_active(contact: ContactRow) -> bool:
    return _normalized_label(contact.status) == "actif"


def _is_admin(contact: ContactRow) -> bool:
    return _normalized_label(contact.full_access) in {"oui", "yes", "true", "1"}


def _role_for(contact: ContactRow) -> UserRole:
    return UserRole.ADMIN if _is_admin(contact) else UserRole.PROF


def _role_value(role: UserRole | str) -> str:
    return role.value if isinstance(role, UserRole) else str(role)


def _diff(target: object, changes: dict[str, object | None], *, ignore_none: bool = True) -> dict[str, tuple[object | None, object | None]]:
    planned: dict[str, tuple[object | None, object | None]] = {}
    for attr, new_value in changes.items():
        if ignore_none and new_value is None:
            continue
        current = getattr(target, attr, None)
        comparable_current = _role_value(current) if attr == "role" else current
        comparable_new = _role_value(new_value) if attr == "role" else new_value
        if comparable_current != comparable_new:
            planned[attr] = (current, new_value)
    return planned


def _apply_changes(target: object, planned: dict[str, tuple[object | None, object | None]]) -> None:
    for attr, (_, new_value) in planned.items():
        setattr(target, attr, new_value)


def _print_event(event: str, payload: dict[str, Any]) -> None:
    details = "|".join(f"{key}={value}" for key, value in payload.items())
    print(f"[{SCRIPT_PREFIX}] {event}|{details}")


def _sync_user(db, *, contact: ContactRow, first_name: str, last_name: str, email: str, apply: bool) -> tuple[str, int]:
    user = db.scalar(
        select(User)
        .where(func.lower(User.email) == email)
        .with_for_update()
        .limit(1)
    )
    desired_role = _role_for(contact)
    active = _is_active(contact)
    phone = _clean(contact.phone)

    if user is None:
        _print_event(
            "create_user",
            {"email": email, "name": contact.full_name, "role": desired_role.value, "active": active},
        )
        if apply:
            user = User(
                email=email,
                hashed_password=hash_password(secrets.token_urlsafe(24)),
                role=desired_role,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                mobile_phone_1=phone,
                is_active=active,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(user)
        return "created", 1

    planned = _diff(
        user,
        {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "mobile_phone_1": phone,
            "role": desired_role,
            "is_active": active,
        },
    )
    if not planned:
        _print_event("user_ok", {"email": email})
        return "unchanged", 0

    _print_event(
        "update_user",
        {"email": email, "changes": ",".join(sorted(planned.keys()))},
    )
    if apply:
        _apply_changes(user, planned)
        user.updated_at = _utcnow()
        db.add(user)
    return "updated", len(planned)


def _sync_professor(db, *, contact: ContactRow, apply: bool) -> dict[str, int]:
    email = _normalized_email(contact.email)
    first_name, last_name = _split_full_name(contact.full_name)
    phone = _clean(contact.phone)
    address_line = _clean(contact.address_line)
    active = _is_active(contact)
    professor = db.scalar(
        select(Professor)
        .where(func.lower(Professor.email) == email)
        .with_for_update()
        .limit(1)
    )

    counters = {
        "professors_created": 0,
        "professors_updated": 0,
        "professors_unchanged": 0,
        "users_created": 0,
        "users_updated": 0,
        "users_unchanged": 0,
        "permission_rows_created": 0,
    }

    created_professor = professor is None
    if professor is None:
        _print_event(
            "create_professor",
            {"email": email, "name": contact.full_name, "active": active, "admin": _is_admin(contact)},
        )
        counters["professors_created"] += 1
        counters["permission_rows_created"] += 1
        _print_event("create_permission_row", {"email": email})
        if apply:
            professor = Professor(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                address_line=address_line,
                teacher_company_name=contact.full_name,
                teacher_company_address=address_line,
                payout_currency="EUR",
                is_coach=_normalized_label(contact.role) == "teacher",
                active=active,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            db.add(professor)
            db.flush()
    else:
        planned = _diff(
            professor,
            {
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "address_line": address_line,
                "is_coach": _normalized_label(contact.role) == "teacher",
                "active": active,
            },
        )
        fill_only = _diff(
            professor,
            {
                "teacher_company_name": contact.full_name if not professor.teacher_company_name else None,
                "teacher_company_address": address_line if address_line and not professor.teacher_company_address else None,
            },
        )
        planned.update(fill_only)
        if planned:
            _print_event(
                "update_professor",
                {"email": email, "changes": ",".join(sorted(planned.keys()))},
            )
            counters["professors_updated"] += 1
            if apply:
                _apply_changes(professor, planned)
                professor.updated_at = _utcnow()
                db.add(professor)
        else:
            _print_event("professor_ok", {"email": email})
            counters["professors_unchanged"] += 1

    user_state, _ = _sync_user(
        db,
        contact=contact,
        first_name=first_name,
        last_name=last_name,
        email=email,
        apply=apply,
    )
    counters[f"users_{user_state}"] += 1

    if professor is not None and not created_professor:
        existing_permission = db.scalar(
            select(ProfessorPermission)
            .where(ProfessorPermission.professor_id == professor.id)
            .limit(1)
        )
        if existing_permission is None:
            counters["permission_rows_created"] += 1
            _print_event("create_permission_row", {"email": email})
            if apply:
                ensure_permissions_row(
                    db,
                    professor_id=professor.id,
                    defaults=DEFAULT_PROFESSOR_PERMISSIONS,
                )
    elif professor is not None and created_professor and apply:
        ensure_permissions_row(
            db,
            professor_id=professor.id,
            defaults=DEFAULT_PROFESSOR_PERMISSIONS,
        )

    return counters


def sync_contacts(*, apply: bool) -> dict[str, int]:
    totals = {
        "rows": len(CONTACTS),
        "unique_rows": 0,
        "duplicates_skipped": 0,
        "professors_created": 0,
        "professors_updated": 0,
        "professors_unchanged": 0,
        "users_created": 0,
        "users_updated": 0,
        "users_unchanged": 0,
        "permission_rows_created": 0,
    }
    seen_emails: set[str] = set()
    with SessionLocal() as db:
        for contact in CONTACTS:
            email = _normalized_email(contact.email)
            if email in seen_emails:
                totals["duplicates_skipped"] += 1
                _print_event("skip_duplicate_row", {"email": email, "name": contact.full_name})
                continue
            seen_emails.add(email)
            totals["unique_rows"] += 1
            counters = _sync_professor(db, contact=contact, apply=apply)
            for key, value in counters.items():
                if key in totals:
                    totals[key] += value
        if apply:
            db.commit()
        else:
            db.rollback()
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronise les contacts enseignants 2026 en production.")
    parser.add_argument("--apply", action="store_true", help="Ecrit les changements en base. Sans cette option: dry-run.")
    parser.add_argument("--json", action="store_true", help="Affiche le resume final en JSON.")
    args = parser.parse_args()

    _print_event("mode", {"apply": args.apply})
    totals = sync_contacts(apply=args.apply)
    if args.json:
        print(json.dumps(totals, ensure_ascii=False, sort_keys=True))
    else:
        _print_event("summary", totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
