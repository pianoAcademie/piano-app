from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.services.gift_cards import gift_card_code_suffix, normalize_gift_card_code


MAX_GIFT_CARD_IMPORT_ROWS = 500


def _header_key(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


HEADER_ALIASES = {
    "code": {
        "code",
        "gift card code",
        "code carte cadeau",
        "code de la carte cadeau",
    },
    "external_order_ref": {
        "order id",
        "order number",
        "numero de commande",
        "commande wordpress",
    },
    "external_line_ref": {
        "line id",
        "line number",
        "ligne de commande",
    },
    "payment_status": {
        "status",
        "order status",
        "etat de la commande",
        "statut paiement",
    },
    "product_name": {
        "product",
        "product name",
        "nom de l element",
        "article",
    },
    "paid_at": {
        "paid at",
        "date paid",
        "date de paiement",
        "date de commande",
    },
    "face_value_ttc": {
        "face value ttc",
        "gift amount",
        "montant carte cadeau",
        "valeur de l offre ttc",
    },
    "purchase_price_ttc": {
        "purchase price ttc",
        "order total",
        "montant total de la commande",
        "prix paye ttc",
    },
}

PAID_STATUSES = {
    "completed",
    "processing",
    "terminee",
    "en cours",
    "payee",
    "paye",
}


@dataclass(frozen=True)
class GiftCardCsvCandidate:
    row_number: int
    code: str | None
    code_suffix: str | None
    external_order_ref: str | None
    external_line_ref: str
    payment_status: str | None
    product_name: str | None
    paid_at: str | None
    face_value_ttc: Decimal | None
    purchase_price_ttc: Decimal | None
    errors: tuple[str, ...]


def _value(row: dict[str, str], canonical: str) -> str | None:
    aliases = HEADER_ALIASES[canonical]
    for header, value in row.items():
        if _header_key(header or "") not in aliases:
            continue
        normalized = str(value or "").strip()
        return normalized or None
    return None


def _decimal(value: str | None, *, label: str, errors: list[str]) -> Decimal | None:
    if value is None:
        errors.append(f"Colonne obligatoire manquante : {label}.")
        return None
    normalized = value.replace("\u202f", "").replace(" ", "").replace(",", ".")
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        errors.append(f"Montant invalide pour {label}.")
        return None
    if amount < 0:
        errors.append(f"{label} ne peut pas être négatif.")
        return None
    return amount.quantize(Decimal("0.01"))


def parse_gift_card_csv(content: bytes) -> list[GiftCardCsvCandidate]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Le fichier doit être encodé en UTF-8.") from exc
    if not text.strip():
        raise ValueError("Le fichier CSV est vide.")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("Le fichier CSV ne contient pas d'en-têtes.")

    rows = list(reader)
    if len(rows) > MAX_GIFT_CARD_IMPORT_ROWS:
        raise ValueError(f"Le fichier est limité à {MAX_GIFT_CARD_IMPORT_ROWS} lignes.")

    candidates: list[GiftCardCsvCandidate] = []
    for row_number, row in enumerate(rows, start=2):
        errors: list[str] = []
        raw_code = _value(row, "code")
        normalized_code: str | None = None
        suffix: str | None = None
        if raw_code is None:
            errors.append("Code de carte cadeau manquant.")
        else:
            try:
                normalized_code = normalize_gift_card_code(raw_code)
                suffix = gift_card_code_suffix(raw_code)
            except ValueError:
                errors.append("Code de carte cadeau invalide ou trop court.")

        order_ref = _value(row, "external_order_ref")
        if order_ref is None:
            errors.append("Numéro de commande WordPress manquant.")
        line_ref = _value(row, "external_line_ref") or "1"
        payment_status = _value(row, "payment_status")
        normalized_status = _header_key(payment_status or "")
        if normalized_status not in PAID_STATUSES:
            errors.append("Le statut de la commande ne confirme pas le paiement.")
        paid_at = _value(row, "paid_at")
        if paid_at is None:
            errors.append("Date de paiement manquante.")

        candidates.append(
            GiftCardCsvCandidate(
                row_number=row_number,
                code=normalized_code,
                code_suffix=suffix,
                external_order_ref=order_ref,
                external_line_ref=line_ref,
                payment_status=payment_status,
                product_name=_value(row, "product_name"),
                paid_at=paid_at,
                face_value_ttc=_decimal(
                    _value(row, "face_value_ttc"),
                    label="la valeur offerte TTC",
                    errors=errors,
                ),
                purchase_price_ttc=_decimal(
                    _value(row, "purchase_price_ttc"),
                    label="le prix payé TTC",
                    errors=errors,
                ),
                errors=tuple(errors),
            )
        )
    return candidates
