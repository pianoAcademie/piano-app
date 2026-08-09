from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path, PurePosixPath
import re
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client_record import ClientLegacyInvoice
from app.models.user import User, UserRole
from app.schemas.sportigo import SportigoInvoiceImportOut


MAX_ARCHIVE_ENTRIES = 2500
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
REQUIRED_COLUMNS = {
    "sportigo_member_id",
    "invoice_number",
    "issued_at",
    "label",
    "total_incl_vat",
    "currency",
    "file_name",
}


@dataclass(frozen=True)
class LegacyInvoiceRow:
    row_number: int
    member_id: str
    invoice_number: str
    issued_at: datetime
    label: str
    total_incl_vat: Decimal
    currency: str
    file_name: str


def _safe_pdf_name(value: str) -> str | None:
    candidate = str(value or "").strip()
    path = PurePosixPath(candidate)
    if not candidate or path.is_absolute() or ".." in path.parts or path.name != candidate:
        return None
    if not candidate.lower().endswith(".pdf"):
        return None
    if re.fullmatch(r"[A-Za-z0-9._-]+\.pdf", candidate) is None:
        return None
    return candidate


def _parse_manifest(raw: bytes) -> tuple[list[LegacyInvoiceRow], list[str]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["manifest.csv doit etre encode en UTF-8."]
    reader = csv.DictReader(StringIO(text), delimiter=";")
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        return [], [f"Colonnes manquantes dans manifest.csv: {', '.join(sorted(missing))}."]
    rows: list[LegacyInvoiceRow] = []
    errors: list[str] = []
    seen: set[str] = set()
    for row_number, raw_row in enumerate(reader, start=2):
        member_id = str(raw_row.get("sportigo_member_id") or "").strip()
        invoice_number = str(raw_row.get("invoice_number") or "").strip()
        file_name = _safe_pdf_name(str(raw_row.get("file_name") or ""))
        if not member_id or not invoice_number or file_name is None:
            errors.append(f"Ligne {row_number}: identifiant, numero de facture ou fichier PDF invalide.")
            continue
        if invoice_number in seen:
            errors.append(f"Ligne {row_number}: facture {invoice_number} en double dans le manifeste.")
            continue
        seen.add(invoice_number)
        try:
            issued_at = datetime.fromisoformat(str(raw_row.get("issued_at") or "").strip())
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=timezone.utc)
            amount = Decimal(str(raw_row.get("total_incl_vat") or "").strip()).quantize(Decimal("0.01"))
        except (ValueError, InvalidOperation):
            errors.append(f"Ligne {row_number}: date ou montant invalide.")
            continue
        label = str(raw_row.get("label") or "").strip()
        currency = str(raw_row.get("currency") or "EUR").strip().upper()
        # A signed amount is intentional here: Sportigo exports credit notes in
        # the same archive as invoices.  Keeping the amount negative lets every
        # consumer distinguish an avoir from a paid invoice without relying on
        # wording in the PDF or label.
        if not label or len(currency) != 3 or amount == Decimal("0.00"):
            errors.append(f"Ligne {row_number}: libelle, devise ou montant invalide.")
            continue
        rows.append(LegacyInvoiceRow(row_number, member_id, invoice_number, issued_at, label, amount, currency, file_name))
    return rows, errors


def import_legacy_invoice_archive(
    db: Session,
    *,
    content: bytes,
    dry_run: bool,
    batch_reference: str,
    storage_dir: Path,
) -> SportigoInvoiceImportOut:
    out = SportigoInvoiceImportOut(dry_run=dry_run, batch_reference=batch_reference)
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile:
        out.errors.append("Archive ZIP invalide.")
        return out
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES or sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            out.errors.append("Archive trop volumineuse.")
            return out
        names = {info.filename for info in infos if not info.is_dir()}
        if "manifest.csv" not in names:
            out.errors.append("manifest.csv est absent de l archive.")
            return out
        rows, parse_errors = _parse_manifest(archive.read("manifest.csv"))
        out.rows_seen = len(rows) + len(parse_errors)
        if parse_errors:
            out.errors.extend(parse_errors[:50])
            return out
        out.rows_valid = len(rows)

        matched_users: dict[str, User] = {}
        pdf_bytes_by_name: dict[str, bytes] = {}
        for row in rows:
            if row.file_name not in names:
                out.errors.append(f"Ligne {row.row_number}: fichier {row.file_name} absent de l archive.")
                continue
            pdf_bytes = archive.read(row.file_name)
            if not pdf_bytes.startswith(b"%PDF-"):
                out.errors.append(f"Ligne {row.row_number}: {row.file_name} n est pas un PDF valide.")
                continue
            user = db.scalar(
                select(User).where(
                    User.role == UserRole.CLIENT,
                    User.private_note.ilike(f"%SPORTIGO_MEMBER_ID:{row.member_id}%"),
                )
            )
            if user is None:
                out.errors.append(f"Ligne {row.row_number}: client Sportigo {row.member_id} introuvable.")
                continue
            matched_users[row.member_id] = user
            pdf_bytes_by_name[row.file_name] = pdf_bytes
        out.clients_matched = len(matched_users)
        if out.errors:
            return out

        existing_by_ref = {
            invoice.external_reference: invoice
            for invoice in db.scalars(
                select(ClientLegacyInvoice).where(
                    ClientLegacyInvoice.source == "SPORTIGO",
                    ClientLegacyInvoice.external_reference.in_([row.invoice_number for row in rows]),
                )
            ).all()
        }
        for row in rows:
            pdf_bytes = pdf_bytes_by_name[row.file_name]
            storage_key = f"{sha256(pdf_bytes).hexdigest()}.pdf"
            existing = existing_by_ref.get(row.invoice_number)
            if existing is None:
                out.invoices_created += 1
            else:
                changed = any(
                    [
                        existing.user_id != matched_users[row.member_id].id,
                        existing.issued_at != row.issued_at,
                        existing.label != row.label,
                        Decimal(existing.total_incl_vat) != row.total_incl_vat,
                        existing.currency != row.currency,
                        existing.pdf_storage_key != storage_key,
                    ]
                )
                if changed:
                    out.invoices_updated += 1
                else:
                    out.invoices_unchanged += 1
            if dry_run:
                continue
            storage_dir.mkdir(parents=True, exist_ok=True)
            target = storage_dir / storage_key
            if not target.exists():
                target.write_bytes(pdf_bytes)
            invoice = existing or ClientLegacyInvoice(source="SPORTIGO", external_reference=row.invoice_number)
            invoice.user_id = matched_users[row.member_id].id
            invoice.source_customer_id = row.member_id
            invoice.issued_at = row.issued_at
            invoice.label = row.label
            invoice.total_incl_vat = row.total_incl_vat
            invoice.currency = row.currency
            invoice.pdf_storage_key = storage_key
            invoice.original_file_name = row.file_name
            db.add(invoice)
        if dry_run:
            db.rollback()
        else:
            db.commit()
    return out
