from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import re
import unicodedata
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting, LegalEntity
from app.services.i18n import normalize_language

INVOICE_TEMPLATE_SETTING_KEY = "config_invoice_template_text_v1"
INVOICE_NUMBER_FORMAT_SETTING_KEY = "config_invoice_number_format_v1"
INVOICE_NUMBER_NEXT_SETTING_KEY = "config_invoice_number_next_v1"
DEFAULT_BILLING_ENTITY_CODE = "ENTITE_NON_DEFINIE"
DEFAULT_INVOICE_NUMBER_FORMAT = "PIANOACADEMIE-%YY%-%NNNN%"
DEFAULT_INVOICE_NUMBER_NEXT = 1
INVOICE_TEMPLATE_VARIABLES_HINT = (
    "{invoice_number} {issued_at} {client_name} {client_id} {payment_type} {label} {payment_status} "
    "{amount_excl_vat} {vat_amount} {total_incl_vat} {currency} {reference} {refund_info} "
    "{company_name} {company_email} {company_address}"
)

DEFAULT_INVOICE_TEMPLATE = (
    "Piano Academie - Facture\n"
    "Numero: {invoice_number}\n"
    "Date: {issued_at}\n"
    "Client: {client_name} ({client_id})\n"
    "Type: {payment_type}\n"
    "Libelle: {label}\n"
    "Statut: {payment_status}\n"
    "Montant HT: {amount_excl_vat} {currency}\n"
    "TVA: {vat_amount} {currency}\n"
    "Total TTC: {total_incl_vat} {currency}\n"
    "Reference: {reference}\n"
    "{refund_info}\n"
    "\n"
    "{company_name}\n"
    "Contact: {company_email}\n"
    "{company_address}\n"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _setting_value(db: Session, key: str, default: str) -> str:
    row = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        return default
    value = row.value.strip()
    return value or default


def normalize_billing_entity(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    return normalized or DEFAULT_BILLING_ENTITY_CODE


def _billing_entity_code(value: str | None) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", (value or "").strip().upper())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _is_legacy_services_entity(value: str | None) -> bool:
    code = _billing_entity_code(value)
    return code in {"PIANO_ACADEMIE_SERVICES", "SERVICES"}


def _first_non_empty_setting_value(db: Session, keys: list[str], default: str = "") -> str:
    for key in keys:
        value = _setting_value(db, key, "").strip()
        if value:
            return value
    return default


def get_invoice_template(db: Session) -> tuple[str, datetime | None]:
    row = db.scalar(select(AppSetting).where(AppSetting.key == INVOICE_TEMPLATE_SETTING_KEY))
    if row is None:
        return DEFAULT_INVOICE_TEMPLATE, None
    value = row.value.strip() or DEFAULT_INVOICE_TEMPLATE
    return value, row.updated_at


def save_invoice_template(db: Session, *, body: str) -> datetime:
    normalized = body.strip()
    if not normalized:
        normalized = DEFAULT_INVOICE_TEMPLATE
    row = db.scalar(select(AppSetting).where(AppSetting.key == INVOICE_TEMPLATE_SETTING_KEY).with_for_update())
    now = _utcnow()
    if row is None:
        db.add(AppSetting(key=INVOICE_TEMPLATE_SETTING_KEY, value=normalized, updated_at=now))
        return now
    row.value = normalized
    row.updated_at = now
    return now


def _normalize_invoice_number_format(value: str | None) -> str:
    candidate = (value or "").strip().upper()
    if not candidate:
        return DEFAULT_INVOICE_NUMBER_FORMAT
    return candidate[:120]


def _normalize_invoice_number_next(value: str | int | None) -> int:
    if value is None:
        return DEFAULT_INVOICE_NUMBER_NEXT
    try:
        number = int(str(value).strip())
    except ValueError:
        return DEFAULT_INVOICE_NUMBER_NEXT
    if number < 1:
        return DEFAULT_INVOICE_NUMBER_NEXT
    return min(number, 999_999_999)


def _format_invoice_number(pattern: str, *, issued_at: datetime, next_number: int) -> str:
    rendered = _normalize_invoice_number_format(pattern)
    rendered = rendered.replace("%YYYY%", issued_at.strftime("%Y"))
    rendered = rendered.replace("%YY%", issued_at.strftime("%y"))
    rendered = rendered.replace("%MM%", issued_at.strftime("%m"))
    rendered = rendered.replace("%DD%", issued_at.strftime("%d"))

    def _replace_sequence_token(match: re.Match[str]) -> str:
        token = match.group(0)
        width = max(len(token) - 2, 1)
        return str(next_number).zfill(width)

    rendered = re.sub(r"%N+%", _replace_sequence_token, rendered)
    if "%N" in rendered:
        rendered = rendered.replace("%N", str(next_number))
    return rendered


def get_invoice_numbering(db: Session) -> tuple[str, int, datetime | None]:
    format_row = db.scalar(select(AppSetting).where(AppSetting.key == INVOICE_NUMBER_FORMAT_SETTING_KEY))
    next_row = db.scalar(select(AppSetting).where(AppSetting.key == INVOICE_NUMBER_NEXT_SETTING_KEY))
    pattern = _normalize_invoice_number_format(format_row.value if format_row else None)
    next_number = _normalize_invoice_number_next(next_row.value if next_row else None)

    updated_candidates = [row.updated_at for row in [format_row, next_row] if row is not None]
    updated_at = max(updated_candidates) if updated_candidates else None
    return pattern, next_number, updated_at


def save_invoice_numbering(db: Session, *, pattern: str, next_number: int) -> datetime:
    normalized_pattern = _normalize_invoice_number_format(pattern)
    normalized_next = _normalize_invoice_number_next(next_number)
    now = _utcnow()

    format_row = db.scalar(
        select(AppSetting).where(AppSetting.key == INVOICE_NUMBER_FORMAT_SETTING_KEY).with_for_update()
    )
    if format_row is None:
        db.add(AppSetting(key=INVOICE_NUMBER_FORMAT_SETTING_KEY, value=normalized_pattern, updated_at=now))
    else:
        format_row.value = normalized_pattern
        format_row.updated_at = now

    next_row = db.scalar(
        select(AppSetting).where(AppSetting.key == INVOICE_NUMBER_NEXT_SETTING_KEY).with_for_update()
    )
    if next_row is None:
        db.add(AppSetting(key=INVOICE_NUMBER_NEXT_SETTING_KEY, value=str(normalized_next), updated_at=now))
    else:
        next_row.value = str(normalized_next)
        next_row.updated_at = now

    return now


def preview_invoice_number(*, pattern: str, next_number: int, issued_at: datetime | None = None) -> str:
    effective_issued_at = issued_at or _utcnow()
    return _format_invoice_number(pattern, issued_at=effective_issued_at, next_number=_normalize_invoice_number_next(next_number))


def reserve_next_invoice_number(db: Session, *, issued_at: datetime | None = None) -> str:
    effective_issued_at = issued_at or _utcnow()
    now = _utcnow()

    format_row = db.scalar(
        select(AppSetting).where(AppSetting.key == INVOICE_NUMBER_FORMAT_SETTING_KEY).with_for_update()
    )
    next_row = db.scalar(
        select(AppSetting).where(AppSetting.key == INVOICE_NUMBER_NEXT_SETTING_KEY).with_for_update()
    )

    pattern = _normalize_invoice_number_format(format_row.value if format_row else None)
    next_number = _normalize_invoice_number_next(next_row.value if next_row else None)
    invoice_number = _format_invoice_number(pattern, issued_at=effective_issued_at, next_number=next_number)

    if format_row is None:
        db.add(AppSetting(key=INVOICE_NUMBER_FORMAT_SETTING_KEY, value=pattern, updated_at=now))
    else:
        format_row.value = pattern
        format_row.updated_at = now

    next_value = str(next_number + 1)
    if next_row is None:
        db.add(AppSetting(key=INVOICE_NUMBER_NEXT_SETTING_KEY, value=next_value, updated_at=now))
    else:
        next_row.value = next_value
        next_row.updated_at = now

    return invoice_number


def render_invoice_text(
    db: Session,
    *,
    invoice_number: str,
    issued_at: datetime,
    client_id: str,
    client_name: str,
    payment_type: str,
    label: str,
    payment_status: str,
    amount_excl_vat: Decimal,
    vat_amount: Decimal,
    total_incl_vat: Decimal,
    currency: str,
    reference: str | None,
    refunded_at: datetime | None,
    refund_reason: str | None,
    legal_entity_id: UUID | None = None,
    billing_entity: str | None = None,
    language: str | None = None,
) -> str:
    template, _ = get_invoice_template(db)
    identity = _company_identity(db, legal_entity_id=legal_entity_id, billing_entity=billing_entity)
    normalized_language = normalize_language(language)

    refund_info = ""
    if refunded_at is not None:
        reason = refund_reason or "-"
        refund_info = (
            f"{_invoice_text(normalized_language, 'refunded_on')}: {refunded_at.strftime('%d/%m/%Y %H:%M')} | "
            f"{_invoice_text(normalized_language, 'refund_reason')}: {reason}"
        )

    values = {
        "invoice_number": invoice_number,
        "issued_at": issued_at.strftime("%d/%m/%Y %H:%M"),
        "client_name": client_name,
        "client_id": client_id,
        "payment_type": payment_type,
        "label": label,
        "payment_status": payment_status,
        "amount_excl_vat": f"{Decimal(amount_excl_vat).quantize(Decimal('0.01'))}",
        "vat_amount": f"{Decimal(vat_amount).quantize(Decimal('0.01'))}",
        "total_incl_vat": f"{Decimal(total_incl_vat).quantize(Decimal('0.01'))}",
        "currency": (currency or "EUR").upper(),
        "reference": reference or "-",
        "refund_info": refund_info,
        "company_name": identity.company_name,
        "company_email": identity.company_email or "-",
        "company_address": identity.company_address,
    }

    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered.rstrip() + "\n"


@dataclass(frozen=True)
class InvoicePeriodLine:
    date_label: str
    type_label: str
    label: str
    quantity: int
    amount_excl_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal
    currency: str
    is_section_header: bool = False
    detail_label: str | None = None


@dataclass(frozen=True)
class InvoiceAppliedPaymentLine:
    date_label: str
    method_label: str
    reference_label: str
    amount: Decimal
    currency: str


def summarize_invoice_period_lines(
    lines: list[InvoicePeriodLine],
) -> tuple[dict[str, dict[str, Decimal]], dict[str, dict[Decimal, dict[str, Decimal]]]]:
    totals_by_currency: dict[str, dict[str, Decimal]] = {}
    totals_by_currency_and_vat_rate: dict[str, dict[Decimal, dict[str, Decimal]]] = {}

    for line in lines:
        if line.is_section_header:
            continue
        currency = _ascii_safe((line.currency or "EUR").strip().upper()) or "EUR"
        vat_rate = Decimal(line.vat_rate).quantize(Decimal("0.01"))
        amount_excl_vat = Decimal(line.amount_excl_vat).quantize(Decimal("0.01"))
        vat_amount = Decimal(line.vat_amount).quantize(Decimal("0.01"))
        total_incl_vat = Decimal(line.total_incl_vat).quantize(Decimal("0.01"))

        currency_totals = totals_by_currency.setdefault(
            currency,
            {
                "amount_excl_vat": Decimal("0.00"),
                "vat_amount": Decimal("0.00"),
                "total_incl_vat": Decimal("0.00"),
            },
        )
        currency_totals["amount_excl_vat"] = (currency_totals["amount_excl_vat"] + amount_excl_vat).quantize(
            Decimal("0.01")
        )
        currency_totals["vat_amount"] = (currency_totals["vat_amount"] + vat_amount).quantize(Decimal("0.01"))
        currency_totals["total_incl_vat"] = (currency_totals["total_incl_vat"] + total_incl_vat).quantize(
            Decimal("0.01")
        )

        vat_totals = totals_by_currency_and_vat_rate.setdefault(currency, {}).setdefault(
            vat_rate,
            {
                "amount_excl_vat": Decimal("0.00"),
                "vat_amount": Decimal("0.00"),
                "total_incl_vat": Decimal("0.00"),
            },
        )
        vat_totals["amount_excl_vat"] = (vat_totals["amount_excl_vat"] + amount_excl_vat).quantize(Decimal("0.01"))
        vat_totals["vat_amount"] = (vat_totals["vat_amount"] + vat_amount).quantize(Decimal("0.01"))
        vat_totals["total_incl_vat"] = (vat_totals["total_incl_vat"] + total_incl_vat).quantize(Decimal("0.01"))

    return totals_by_currency, totals_by_currency_and_vat_rate


class _SimplePdfDocument:
    width = 595.0
    height = 842.0

    def __init__(self) -> None:
        self._pages: list[list[str]] = []
        self._page_links: list[list[tuple[float, float, float, float, str]]] = []
        self._images: dict[str, tuple[bytes, int, int]] = {}
        self.new_page()

    def new_page(self) -> None:
        self._pages.append([])
        self._page_links.append([])

    def _current_page(self) -> list[str]:
        return self._pages[-1]

    def _push(self, op: str) -> None:
        self._current_page().append(op)

    def _push_on_page(self, page_index: int, op: str) -> None:
        self._pages[page_index].append(op)

    def _to_y(self, top_y: float) -> float:
        return self.height - top_y

    def text(
        self,
        *,
        x: float,
        top_y: float,
        value: str,
        size: float = 10.0,
        bold: bool = False,
        color: tuple[float, float, float] = (0.1, 0.14, 0.2),
    ) -> None:
        font = "F2" if bold else "F1"
        r, g, b = color
        safe = _pdf_escape(_ascii_safe(value))
        y = self._to_y(top_y)
        self._push(
            f"BT /{font} {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x:.2f} {y:.2f} Tm ({safe}) Tj ET"
        )

    def text_right(
        self,
        *,
        right_x: float,
        top_y: float,
        value: str,
        size: float = 10.0,
        bold: bool = False,
        color: tuple[float, float, float] = (0.1, 0.14, 0.2),
    ) -> None:
        width = _text_width_estimate(value, size=size)
        self.text(x=max(0.0, right_x - width), top_y=top_y, value=value, size=size, bold=bold, color=color)

    def line(
        self,
        *,
        x1: float,
        top_y1: float,
        x2: float,
        top_y2: float,
        width: float = 1.0,
        color: tuple[float, float, float] = (0.82, 0.86, 0.91),
    ) -> None:
        r, g, b = color
        y1 = self._to_y(top_y1)
        y2 = self._to_y(top_y2)
        self._push(f"{width:.2f} w {r:.3f} {g:.3f} {b:.3f} RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect(
        self,
        *,
        x: float,
        top_y: float,
        width: float,
        height: float,
        stroke_color: tuple[float, float, float] = (0.82, 0.86, 0.91),
        fill_color: tuple[float, float, float] | None = None,
        stroke_width: float = 1.0,
    ) -> None:
        y = self._to_y(top_y + height)
        sr, sg, sb = stroke_color
        prefix = f"{stroke_width:.2f} w {sr:.3f} {sg:.3f} {sb:.3f} RG "
        if fill_color is None:
            self._push(f"{prefix}{x:.2f} {y:.2f} {width:.2f} {height:.2f} re S")
            return
        fr, fg, fb = fill_color
        self._push(f"{prefix}{fr:.3f} {fg:.3f} {fb:.3f} rg {x:.2f} {y:.2f} {width:.2f} {height:.2f} re B")

    def add_link(
        self,
        *,
        x: float,
        top_y: float,
        width: float,
        height: float,
        url: str,
    ) -> None:
        normalized = _ascii_safe((url or "").strip())
        if not normalized:
            return
        self._page_links[-1].append((x, top_y, width, height, normalized))

    def register_jpeg_image(self, *, image_bytes: bytes, width_px: int, height_px: int) -> str:
        image_name = f"Im{len(self._images) + 1}"
        self._images[image_name] = (image_bytes, max(1, width_px), max(1, height_px))
        return image_name

    def draw_image(
        self,
        *,
        image_name: str,
        x: float,
        top_y: float,
        width: float,
        height: float,
    ) -> None:
        if image_name not in self._images:
            return
        y = self._to_y(top_y + height)
        self._push(f"q {width:.2f} 0 0 {height:.2f} {x:.2f} {y:.2f} cm /{image_name} Do Q")

    def add_page_numbers(self) -> None:
        total_pages = len(self._pages)
        if total_pages <= 1:
            return
        for page_index in range(total_pages):
            text = f"Page {page_index + 1}/{total_pages}"
            safe = _pdf_escape(_ascii_safe(text))
            x = self.width - 94.0
            y = 20.0
            op = f"BT /F1 8.00 Tf 0.420 0.470 0.560 rg 1 0 0 1 {x:.2f} {y:.2f} Tm ({safe}) Tj ET"
            self._push_on_page(page_index, op)

    def build(self) -> bytes:
        object_map: dict[int, bytes] = {}
        object_map[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
        object_map[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        object_map[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"

        next_id = 5
        image_object_ids: dict[str, int] = {}
        for image_name, (image_bytes, width_px, height_px) in self._images.items():
            image_object_id = next_id
            next_id += 1
            object_map[image_object_id] = (
                b"<< /Type /XObject /Subtype /Image "
                + f"/Width {width_px} /Height {height_px} ".encode("ascii")
                + b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
                + b"/Length "
                + str(len(image_bytes)).encode("ascii")
                + b" >>\nstream\n"
                + image_bytes
                + b"\nendstream"
            )
            image_object_ids[image_name] = image_object_id

        page_ids: list[int] = []
        for page_index, page_ops in enumerate(self._pages):
            content_id = next_id
            page_id = next_id + 1
            next_id += 2
            stream_data = ("\n".join(page_ops) + "\n").encode("latin-1", "replace")
            object_map[content_id] = (
                b"<< /Length " + str(len(stream_data)).encode("ascii") + b" >>\nstream\n" + stream_data + b"endstream"
            )
            xobject_resources = b""
            if image_object_ids:
                refs = " ".join(f"/{name} {obj_id} 0 R" for name, obj_id in image_object_ids.items())
                xobject_resources = f" /XObject << {refs} >>".encode("ascii")
            annotation_refs: list[str] = []
            for x, top_y, width, height, url in (self._page_links[page_index] if page_index < len(self._page_links) else []):
                annotation_id = next_id
                next_id += 1
                y_bottom = self._to_y(top_y + height)
                y_top = self._to_y(top_y)
                rect = f"{x:.2f} {y_bottom:.2f} {x + width:.2f} {y_top:.2f}"
                safe_url = _pdf_escape(url)
                object_map[annotation_id] = (
                    f"<< /Type /Annot /Subtype /Link /Rect [{rect}] /Border [0 0 0] "
                    f"/A << /S /URI /URI ({safe_url}) >> >>"
                ).encode("ascii")
                annotation_refs.append(f"{annotation_id} 0 R")
            annotation_block = f" /Annots [{' '.join(annotation_refs)}]".encode("ascii") if annotation_refs else b""
            object_map[page_id] = (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                + b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >>"
                + xobject_resources
                + annotation_block
                + b" >> "
                + f"/Contents {content_id} 0 R >>".encode("ascii")
            )
            page_ids.append(page_id)

        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        object_map[2] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("ascii")

        max_object_id = max(object_map.keys())
        payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0] * (max_object_id + 1)
        for object_id in range(1, max_object_id + 1):
            body = object_map[object_id]
            offsets[object_id] = len(payload)
            payload.extend(f"{object_id} 0 obj\n".encode("ascii"))
            payload.extend(body)
            payload.extend(b"\nendobj\n")

        start_xref = len(payload)
        payload.extend(f"xref\n0 {max_object_id + 1}\n".encode("ascii"))
        payload.extend(b"0000000000 65535 f \n")
        for object_id in range(1, max_object_id + 1):
            payload.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
        payload.extend(f"trailer\n<< /Size {max_object_id + 1} /Root 1 0 R >>\n".encode("ascii"))
        payload.extend(f"startxref\n{start_xref}\n%%EOF".encode("ascii"))
        return bytes(payload)


def _ascii_safe(value: str) -> str:
    cleaned = (value or "").replace("€", "EUR").replace("’", "'").replace("–", "-").replace("—", "-")
    return unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _format_amount(value: Decimal) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


def _text_width_estimate(value: str, *, size: float) -> float:
    # Approximation suffisante pour aligner a droite dans les colonnes numeriques.
    return len(_ascii_safe(value)) * size * 0.52


def _wrap_text(value: str, max_chars: int) -> list[str]:
    raw_words = _ascii_safe(value).split()
    if not raw_words:
        return [""]
    words: list[str] = []
    for word in raw_words:
        if len(word) <= max_chars:
            words.append(word)
            continue
        for start in range(0, len(word), max_chars):
            words.append(word[start : start + max_chars])
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def _wrap_text_preserving_breaks(value: str, max_chars: int) -> list[str]:
    safe = _ascii_safe(value)
    if not safe.strip():
        return []
    lines: list[str] = []
    for raw_line in safe.splitlines():
        wrapped = _wrap_text(raw_line, max_chars)
        if wrapped == [""] and lines:
            lines.append("")
            continue
        lines.extend(wrapped)
    return lines


def _truncate_text(value: str, max_chars: int) -> str:
    safe = _ascii_safe(value)
    if len(safe) <= max_chars:
        return safe
    if max_chars <= 3:
        return safe[:max_chars]
    return safe[: max_chars - 3].rstrip() + "..."


COUNTRY_NAME_BY_CODE = {
    "FR": "France",
    "BE": "Belgique",
    "CH": "Suisse",
    "LU": "Luxembourg",
    "ES": "Espagne",
    "IT": "Italie",
    "GB": "Royaume-Uni",
    "UK": "Royaume-Uni",
    "US": "Etats-Unis",
    "CA": "Canada",
    "DE": "Allemagne",
}

INVOICE_TEXT: dict[str, dict[str, str]] = {
    "fr": {
        "document_title": "FACTURE",
        "number_label": "Numero: {invoice_number}",
        "date_label": "Date: {issued_at}",
        "share_capital_label": "Capital social: {share_capital}",
        "vat_number_label": "TVA intracom: {vat_number}",
        "phone_label": "Telephone: {phone}",
        "invoice_for": "Facture pour",
        "invoice_date": "Date de la facture: {issued_at}",
        "due_date": "Date d echeance: {due_date}",
        "table_date": "Date",
        "table_service": "Prestation",
        "table_qty": "Qt",
        "table_ht": "HT",
        "table_vat_rate": "TVA%",
        "table_vat": "TVA",
        "table_ttc": "TTC",
        "totals_title": "Totaux",
        "totals_currency_vat": "Devise / TVA",
        "balance_title": "Solde",
        "opening_balance": "Ancien Solde",
        "opening_balance_at": "Ancien Solde au {date}",
        "period_amount": "Montant periode facturee ({currency})",
        "applied_payments": "Paiements enregistres ({currency})",
        "applied_payment_details_title": "Paiements recus / imputes",
        "payment_table_date": "Date",
        "payment_table_method": "Mode",
        "payment_table_reference": "Reference",
        "payment_table_amount": "Montant",
        "total_to_pay": "Montant total a payer ({currency})",
        "online_payment_title": "Paiement en ligne",
        "online_payment_button": "Payer en ligne",
        "adjustments_title": "Remises et supplements (detail par type)",
        "adjustment_fallback": "Ajustement",
        "note_title": "Note",
        "footer_phone": "Tel",
        "refunded_on": "Rembourse le",
        "refund_reason": "Motif",
    },
    "en": {
        "document_title": "INVOICE",
        "number_label": "Number: {invoice_number}",
        "date_label": "Date: {issued_at}",
        "share_capital_label": "Share capital: {share_capital}",
        "vat_number_label": "VAT number: {vat_number}",
        "phone_label": "Phone: {phone}",
        "invoice_for": "Bill to",
        "invoice_date": "Invoice date: {issued_at}",
        "due_date": "Due date: {due_date}",
        "table_date": "Date",
        "table_service": "Description",
        "table_qty": "Qty",
        "table_ht": "Excl. VAT",
        "table_vat_rate": "VAT%",
        "table_vat": "VAT",
        "table_ttc": "Incl. VAT",
        "totals_title": "Totals",
        "totals_currency_vat": "Currency / VAT",
        "balance_title": "Balance",
        "opening_balance": "Previous balance",
        "opening_balance_at": "Previous balance on {date}",
        "period_amount": "Billed period amount ({currency})",
        "applied_payments": "Recorded payments ({currency})",
        "applied_payment_details_title": "Received / applied payments",
        "payment_table_date": "Date",
        "payment_table_method": "Method",
        "payment_table_reference": "Reference",
        "payment_table_amount": "Amount",
        "total_to_pay": "Total amount due ({currency})",
        "online_payment_title": "Online payment",
        "online_payment_button": "Pay online",
        "adjustments_title": "Discounts and surcharges (breakdown by type)",
        "adjustment_fallback": "Adjustment",
        "note_title": "Note",
        "footer_phone": "Phone",
        "refunded_on": "Refunded on",
        "refund_reason": "Reason",
    },
}


def _invoice_text(language: str | None, key: str, **values: object) -> str:
    normalized_language = normalize_language(language)
    template = INVOICE_TEXT.get(normalized_language, INVOICE_TEXT["fr"]).get(key, key)
    return template.format(**values)


def _country_display_name(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    normalized = value.upper()
    if len(normalized) == 2:
        return COUNTRY_NAME_BY_CODE.get(normalized, normalized)
    return value[:1].upper() + value[1:].lower()


@dataclass(frozen=True)
class CompanyIdentity:
    company_name: str
    company_email: str
    company_phone: str
    company_siren: str
    company_siret: str
    company_vat_number: str
    company_address: str
    company_legal_form: str | None
    company_share_capital: str | None
    company_logo_jpeg: bytes | None
    company_logo_width_px: int | None
    company_logo_height_px: int | None


COMPANY_IDENTITY_SNAPSHOT_FIELDS = (
    "company_name",
    "company_email",
    "company_phone",
    "company_siren",
    "company_siret",
    "company_vat_number",
    "company_address",
    "company_legal_form",
    "company_share_capital",
)


def serialize_company_identity_snapshot(identity: CompanyIdentity) -> dict[str, str | None]:
    return {
        "company_name": identity.company_name,
        "company_email": identity.company_email,
        "company_phone": identity.company_phone,
        "company_siren": identity.company_siren,
        "company_siret": identity.company_siret,
        "company_vat_number": identity.company_vat_number,
        "company_address": identity.company_address,
        "company_legal_form": identity.company_legal_form,
        "company_share_capital": identity.company_share_capital,
    }


def _decode_jpeg_data_url(value: str | None) -> bytes | None:
    raw = (value or "").strip()
    if not raw:
        return None
    match = re.match(r"^data:image/(?:jpeg|jpg);base64,(?P<data>[A-Za-z0-9+/=\s]+)$", raw, flags=re.IGNORECASE)
    if match is None:
        return None
    base64_payload = re.sub(r"\s+", "", match.group("data"))
    try:
        decoded = base64.b64decode(base64_payload, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(decoded) < 4 or decoded[0:2] != b"\xff\xd8":
        return None
    return decoded


def _jpeg_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    if len(image_bytes) < 4 or image_bytes[0:2] != b"\xff\xd8":
        return None
    index = 2
    marker_with_size_exceptions = {0x01, *range(0xD0, 0xD8), 0xD8, 0xD9}
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while index + 1 < len(image_bytes):
        if image_bytes[index] != 0xFF:
            index += 1
            continue
        while index < len(image_bytes) and image_bytes[index] == 0xFF:
            index += 1
        if index >= len(image_bytes):
            break
        marker = image_bytes[index]
        index += 1
        if marker in marker_with_size_exceptions:
            continue
        if index + 2 > len(image_bytes):
            break
        segment_length = int.from_bytes(image_bytes[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(image_bytes):
            break
        if marker in sof_markers and segment_length >= 7:
            height = int.from_bytes(image_bytes[index + 3 : index + 5], "big")
            width = int.from_bytes(image_bytes[index + 5 : index + 7], "big")
            if width > 0 and height > 0:
                return width, height
            return None
        index += segment_length
    return None


def _resolve_legal_entity(
    db: Session,
    *,
    legal_entity_id: UUID | None = None,
) -> LegalEntity | None:
    if legal_entity_id is None:
        return None
    return db.scalar(select(LegalEntity).where(LegalEntity.id == legal_entity_id))


def _legacy_company_identity_from_settings(
    db: Session,
    *,
    billing_entity: str | None = None,
) -> CompanyIdentity:
    prefer_services_settings = _is_legacy_services_entity(billing_entity)

    def _keys(suffix: str) -> list[str]:
        if prefer_services_settings:
            return [f"config_account_services_{suffix}", f"config_account_{suffix}"]
        return [f"config_account_{suffix}"]

    company_name = _first_non_empty_setting_value(
        db,
        _keys("club_name") + _keys("company_name"),
        "Piano Academie",
    )
    company_email = _first_non_empty_setting_value(db, _keys("contact_email"), "-")
    company_phone = _first_non_empty_setting_value(db, _keys("contact_phone"), "-")
    company_siren = _first_non_empty_setting_value(db, _keys("siren"), "-")
    company_siret = _first_non_empty_setting_value(db, _keys("siret"), "-")
    company_vat_number = _first_non_empty_setting_value(db, _keys("vat_number"), "-")
    address_parts = [
        _first_non_empty_setting_value(db, _keys("address_line"), ""),
        _first_non_empty_setting_value(db, _keys("postal_code"), ""),
        _first_non_empty_setting_value(db, _keys("city"), ""),
        _country_display_name(_first_non_empty_setting_value(db, _keys("country"), "")),
    ]
    company_address = " ".join(part for part in address_parts if part).strip() or "-"
    logo_raw = _first_non_empty_setting_value(db, _keys("logo_data_url"), "")
    logo_jpeg = _decode_jpeg_data_url(logo_raw)
    logo_dimensions = _jpeg_dimensions(logo_jpeg) if logo_jpeg is not None else None
    return CompanyIdentity(
        company_name=company_name,
        company_email=company_email,
        company_phone=company_phone,
        company_siren=company_siren,
        company_siret=company_siret,
        company_vat_number=company_vat_number,
        company_address=company_address,
        company_legal_form=None,
        company_share_capital=None,
        company_logo_jpeg=logo_jpeg,
        company_logo_width_px=logo_dimensions[0] if logo_dimensions else None,
        company_logo_height_px=logo_dimensions[1] if logo_dimensions else None,
    )


def _company_identity(
    db: Session,
    *,
    legal_entity_id: UUID | None = None,
    billing_entity: str | None = None,
) -> CompanyIdentity:
    if legal_entity_id is None:
        # Legacy fallback for historical invoices without legal entity id.
        return _legacy_company_identity_from_settings(db, billing_entity=billing_entity)
    entity = _resolve_legal_entity(db, legal_entity_id=legal_entity_id)
    if entity is None:
        raise ValueError(f"Unknown legal entity id for invoice rendering: {legal_entity_id}")
    legacy_identity = _legacy_company_identity_from_settings(db, billing_entity=billing_entity)

    address = (entity.address_text or "").strip()
    if address and entity.country_code:
        address = f"{address} ({_country_display_name(entity.country_code)})"
    company_address = address or "-"
    company_email = (entity.accounting_email or "").strip() or legacy_identity.company_email or "-"
    company_phone = (entity.phone or "").strip() or legacy_identity.company_phone or "-"
    return CompanyIdentity(
        company_name=(entity.name or "").strip() or "Societe",
        company_email=company_email,
        company_phone=company_phone,
        company_siren=(entity.siren or "").strip() or "-",
        company_siret=(entity.siret or "").strip() or "-",
        company_vat_number=(entity.vat_number or "").strip() or "-",
        company_address=company_address,
        company_legal_form=(entity.legal_form or "").strip() or None,
        company_share_capital=(entity.share_capital or "").strip() or None,
        company_logo_jpeg=legacy_identity.company_logo_jpeg,
        company_logo_width_px=legacy_identity.company_logo_width_px,
        company_logo_height_px=legacy_identity.company_logo_height_px,
    )


def build_company_identity_snapshot(
    db: Session,
    *,
    legal_entity_id: UUID | None = None,
    billing_entity: str | None = None,
) -> dict[str, str | None]:
    return serialize_company_identity_snapshot(
        _company_identity(db, legal_entity_id=legal_entity_id, billing_entity=billing_entity)
    )


def company_identity_from_snapshot(snapshot: object) -> CompanyIdentity | None:
    if not isinstance(snapshot, dict):
        return None
    normalized: dict[str, str | None] = {}
    for field in COMPANY_IDENTITY_SNAPSHOT_FIELDS:
        value = snapshot.get(field)
        if value is None:
            normalized[field] = None
            continue
        normalized[field] = str(value).strip() or None
    if not normalized.get("company_name"):
        return None
    return CompanyIdentity(
        company_name=normalized["company_name"] or "Societe",
        company_email=normalized["company_email"] or "-",
        company_phone=normalized["company_phone"] or "-",
        company_siren=normalized["company_siren"] or "-",
        company_siret=normalized["company_siret"] or "-",
        company_vat_number=normalized["company_vat_number"] or "-",
        company_address=normalized["company_address"] or "-",
        company_legal_form=normalized["company_legal_form"],
        company_share_capital=normalized["company_share_capital"],
        company_logo_jpeg=None,
        company_logo_width_px=None,
        company_logo_height_px=None,
    )


def _company_legal_summary(identity: CompanyIdentity, *, language: str | None = None) -> str:
    parts = [
        identity.company_legal_form or "",
        (
            _invoice_text(language, "share_capital_label", share_capital=identity.company_share_capital)
            if identity.company_share_capital
            else ""
        ),
    ]
    return " | ".join(part for part in parts if part).strip()


def _company_issuer_lines(identity: CompanyIdentity, *, language: str | None = None) -> list[str]:
    lines = [identity.company_name]
    lines.extend(
        [
            f"SIREN: {identity.company_siren}",
            _invoice_text(language, "vat_number_label", vat_number=identity.company_vat_number),
            _invoice_text(language, "phone_label", phone=identity.company_phone),
            f"Email: {identity.company_email}",
        ]
    )
    return lines


def _company_footer_lines(identity: CompanyIdentity, *, language: str | None = None) -> tuple[str, str]:
    line_1_parts = [identity.company_name]
    legal_summary = _company_legal_summary(identity, language=language)
    if legal_summary:
        line_1_parts.append(legal_summary)
    if identity.company_siret:
        line_1_parts.append(f"SIRET: {identity.company_siret}")
    footer_line_1 = " | ".join(part for part in line_1_parts if part).strip()

    line_2_parts = []
    if identity.company_phone:
        line_2_parts.append(f"{_invoice_text(language, 'footer_phone')}: {identity.company_phone}")
    if identity.company_email:
        line_2_parts.append(identity.company_email)
    if identity.company_address:
        line_2_parts.append(identity.company_address)
    footer_line_2 = " | ".join(part for part in line_2_parts if part).strip()
    return footer_line_1, footer_line_2


def render_invoice_period_pdf(
    db: Session,
    *,
    invoice_number: str,
    issued_at: datetime,
    client_id: str,
    client_name: str,
    period_label: str,
    lines: list[InvoicePeriodLine],
    totals_by_currency: dict[str, dict[str, Decimal]],
    opening_balance_by_currency: dict[str, Decimal] | None = None,
    applied_payment_totals_by_currency: dict[str, Decimal] | None = None,
    applied_payment_lines: list[InvoiceAppliedPaymentLine] | None = None,
    total_to_pay_by_currency: dict[str, Decimal] | None = None,
    payment_link_url: str | None = None,
    adjustment_summary: list[tuple[str, str, Decimal]] | None = None,
    note: str | None,
    client_billing_address: str | None = None,
    due_date: date | None = None,
    watermark: str | None = None,
    legal_entity_id: UUID | None = None,
    billing_entity: str | None = None,
    language: str | None = None,
    company_identity_override: CompanyIdentity | None = None,
    company_identity_snapshot: dict[str, object] | None = None,
) -> bytes:
    identity = (
        company_identity_override
        or company_identity_from_snapshot(company_identity_snapshot)
        or _company_identity(
            db,
            legal_entity_id=legal_entity_id,
            billing_entity=billing_entity,
        )
    )
    normalized_language = normalize_language(language)
    pdf = _SimplePdfDocument()
    logo_resource_name: str | None = None
    logo_width = 0.0
    logo_height = 0.0
    if (
        identity.company_logo_jpeg is not None
        and identity.company_logo_width_px is not None
        and identity.company_logo_height_px is not None
    ):
        logo_resource_name = pdf.register_jpeg_image(
            image_bytes=identity.company_logo_jpeg,
            width_px=identity.company_logo_width_px,
            height_px=identity.company_logo_height_px,
        )
        logo_height = 44.0
        logo_width = min(
            150.0,
            logo_height * (identity.company_logo_width_px / max(1, identity.company_logo_height_px)),
        )

    left = 34.0
    right = pdf.width - 34.0
    table_top = 268.0
    row_top = table_top + 22.0

    col_date_x = left + 6
    col_label_x = left + 86
    col_qty_right = left + 361
    col_ht_right = left + 406
    col_vat_rate_right = left + 446
    col_vat_right = left + 486
    col_ttc_right = right - 6
    totals_col_ht_right = right - 166
    totals_col_vat_right = right - 86
    totals_col_ttc_right = right - 6

    summary_page_row_top = 236.0

    def draw_header(*, include_table_header: bool = True) -> None:
        pdf.rect(
            x=0.0,
            top_y=0.0,
            width=pdf.width,
            height=92.0,
            stroke_color=(0.11, 0.15, 0.24),
            fill_color=(0.11, 0.15, 0.24),
            stroke_width=0.0,
        )
        title_x = left
        if logo_resource_name is not None:
            logo_top_y = 22.0
            pdf.draw_image(
                image_name=logo_resource_name,
                x=left,
                top_y=logo_top_y,
                width=logo_width,
                height=logo_height,
            )
            title_x = left + logo_width + 12.0
        pdf.text(x=title_x, top_y=34.0, value=identity.company_name, size=20, bold=True, color=(1, 1, 1))
        pdf.text(
            x=title_x,
            top_y=54.0,
            value=_invoice_text(normalized_language, "document_title"),
            size=12,
            bold=True,
            color=(0.95, 0.78, 0.48),
        )
        pdf.text_right(
            right_x=right - 2.0,
            top_y=30.0,
            value=_truncate_text(
                _invoice_text(normalized_language, "number_label", invoice_number=invoice_number),
                54,
            ),
            size=11,
            bold=True,
            color=(1, 1, 1),
        )
        pdf.text_right(
            right_x=right - 2.0,
            top_y=48.0,
            value=_invoice_text(normalized_language, "date_label", issued_at=issued_at.strftime("%d/%m/%Y")),
            size=10,
            color=(0.92, 0.93, 0.96),
        )

        # Bloc identite emetteur
        issuer_lines = _company_issuer_lines(identity, language=normalized_language)
        issuer_top_y = 116.0
        issuer_line_height = 16.0
        for index, line in enumerate(issuer_lines):
            pdf.text(
                x=left,
                top_y=issuer_top_y + (index * issuer_line_height),
                value=line,
                size=10,
                bold=index == 0,
            )
        address_top_y = issuer_top_y + (len(issuer_lines) * issuer_line_height)
        for index, chunk in enumerate(_wrap_text(identity.company_address, 48)):
            pdf.text(x=left, top_y=address_top_y + (index * 14.0), value=chunk, size=10)

        # Bloc client facture
        billing_address = _ascii_safe((client_billing_address or "").strip()) or "-"
        pdf.text(x=330.0, top_y=116.0, value=_invoice_text(normalized_language, "invoice_for"), size=11, bold=True)
        pdf.text(x=330.0, top_y=134.0, value=client_name, size=10, bold=True)
        for index, chunk in enumerate(_wrap_text(billing_address, 34)):
            pdf.text(x=330.0, top_y=150.0 + (index * 14.0), value=chunk, size=10)
        pdf.text(
            x=330.0,
            top_y=196.0,
            value=_invoice_text(normalized_language, "invoice_date", issued_at=issued_at.strftime("%d/%m/%Y")),
            size=10,
            bold=True,
        )
        pdf.text(
            x=330.0,
            top_y=212.0,
            value=_invoice_text(
                normalized_language,
                "due_date",
                due_date=(due_date or issued_at.date()).strftime("%d/%m/%Y"),
            ),
            size=10,
            bold=True,
        )

        if not include_table_header:
            return

        pdf.rect(
            x=left,
            top_y=table_top,
            width=right - left,
            height=22.0,
            stroke_color=(0.82, 0.86, 0.91),
            fill_color=(0.95, 0.96, 0.98),
        )
        pdf.text(x=col_date_x, top_y=282.0, value=_invoice_text(normalized_language, "table_date"), size=9, bold=True)
        pdf.text(x=col_label_x, top_y=282.0, value=_invoice_text(normalized_language, "table_service"), size=9, bold=True)
        pdf.text_right(right_x=col_qty_right, top_y=282.0, value=_invoice_text(normalized_language, "table_qty"), size=9, bold=True)
        pdf.text_right(right_x=col_ht_right, top_y=282.0, value=_invoice_text(normalized_language, "table_ht"), size=9, bold=True)
        pdf.text_right(
            right_x=col_vat_rate_right,
            top_y=282.0,
            value=_invoice_text(normalized_language, "table_vat_rate"),
            size=9,
            bold=True,
        )
        pdf.text_right(right_x=col_vat_right, top_y=282.0, value=_invoice_text(normalized_language, "table_vat"), size=9, bold=True)
        pdf.text_right(right_x=col_ttc_right, top_y=282.0, value=_invoice_text(normalized_language, "table_ttc"), size=9, bold=True)

    def draw_table_header_for_new_page() -> float:
        draw_header()
        return row_top

    current_row_top = draw_table_header_for_new_page()
    for row in lines:
        if row.is_section_header:
            row_height = 20.0
            if current_row_top + row_height > 760.0:
                pdf.new_page()
                current_row_top = draw_table_header_for_new_page()
            pdf.rect(
                x=left,
                top_y=current_row_top,
                width=right - left,
                height=row_height,
                stroke_color=(0.90, 0.92, 0.95),
                fill_color=(0.98, 0.98, 0.99),
            )
            pdf.text(x=col_label_x, top_y=current_row_top + 14, value=row.label, size=10, bold=True)
            current_row_top += row_height
            continue

        date_lines = _wrap_text(row.date_label, 18)
        label_lines = _wrap_text(row.label, 44)
        detail_lines = _wrap_text_preserving_breaks(row.detail_label or "", 56)
        date_height = len(date_lines) * 12.0
        label_height = len(label_lines) * 12.0
        detail_height = len(detail_lines) * 8.5
        row_height = max(20.0, date_height + 8.0, label_height + detail_height + 8.0)
        if current_row_top + row_height > 760.0:
            pdf.new_page()
            current_row_top = draw_table_header_for_new_page()

        pdf.rect(x=left, top_y=current_row_top, width=right - left, height=row_height, stroke_color=(0.90, 0.92, 0.95))
        for idx, chunk in enumerate(date_lines):
            pdf.text(x=col_date_x, top_y=current_row_top + 14 + (idx * 12), value=chunk, size=9)
        for idx, chunk in enumerate(label_lines):
            pdf.text(x=col_label_x, top_y=current_row_top + 14 + (idx * 12), value=chunk, size=9)
        detail_top_y = current_row_top + 14 + (len(label_lines) * 12)
        for idx, chunk in enumerate(detail_lines):
            pdf.text(
                x=col_label_x,
                top_y=detail_top_y + (idx * 8.5),
                value=chunk,
                size=7,
                color=(0.39, 0.45, 0.54),
            )
        pdf.text_right(right_x=col_qty_right, top_y=current_row_top + 14, value=str(row.quantity), size=9)
        pdf.text_right(right_x=col_ht_right, top_y=current_row_top + 14, value=_format_amount(row.amount_excl_vat), size=9)
        pdf.text_right(right_x=col_vat_rate_right, top_y=current_row_top + 14, value=f"{Decimal(row.vat_rate).quantize(Decimal('0.01'))}%", size=9)
        pdf.text_right(right_x=col_vat_right, top_y=current_row_top + 14, value=_format_amount(row.vat_amount), size=9)
        pdf.text_right(
            right_x=col_ttc_right,
            top_y=current_row_top + 14,
            value=_format_amount(row.total_incl_vat),
            size=9,
            bold=True,
        )
        current_row_top += row_height

    normalized_adjustments: list[tuple[str, str, Decimal]] = []
    for raw in adjustment_summary or []:
        if not isinstance(raw, tuple) or len(raw) != 3:
            continue
        label, currency, amount = raw
        normalized_adjustments.append(
            (
                _ascii_safe(str(label).strip()) or _invoice_text(normalized_language, "adjustment_fallback"),
                _ascii_safe(str(currency).strip().upper()) or "EUR",
                Decimal(amount).quantize(Decimal("0.01")),
            )
        )

    normalized_note = _ascii_safe((note or "").strip())
    period_start_label = ""
    if " - " in period_label:
        period_start_candidate = _ascii_safe(period_label.split(" - ", 1)[0].strip())
        if re.match(r"^\d{2}/\d{2}/\d{4}$", period_start_candidate):
            period_start_label = period_start_candidate
    else:
        period_start_candidate = _ascii_safe(period_label.strip())
        if re.match(r"^\d{2}/\d{2}/\d{4}$", period_start_candidate):
            period_start_label = period_start_candidate
    normalized_opening_balance_by_currency: dict[str, Decimal] = {}
    for currency_code, amount in (opening_balance_by_currency or {}).items():
        currency = _ascii_safe(str(currency_code).strip().upper()) or "EUR"
        normalized_opening_balance_by_currency[currency] = Decimal(amount).quantize(Decimal("0.01"))
    normalized_applied_payment_totals_by_currency: dict[str, Decimal] = {}
    for currency_code, amount in (applied_payment_totals_by_currency or {}).items():
        currency = _ascii_safe(str(currency_code).strip().upper()) or "EUR"
        normalized_applied_payment_totals_by_currency[currency] = Decimal(amount).quantize(Decimal("0.01"))
    normalized_applied_payment_lines: list[InvoiceAppliedPaymentLine] = []
    for payment_line in applied_payment_lines or []:
        amount = Decimal(payment_line.amount).quantize(Decimal("0.01"))
        if amount == Decimal("0.00"):
            continue
        normalized_applied_payment_lines.append(
            InvoiceAppliedPaymentLine(
                date_label=_truncate_text(payment_line.date_label, 16),
                method_label=_truncate_text(payment_line.method_label, 24),
                reference_label=_truncate_text(payment_line.reference_label, 42),
                amount=amount,
                currency=_ascii_safe(str(payment_line.currency).strip().upper()) or "EUR",
            )
        )
    normalized_total_to_pay_by_currency: dict[str, Decimal] = {}
    computed_totals_by_currency, totals_by_currency_and_vat_rate = summarize_invoice_period_lines(lines)
    effective_totals_by_currency = computed_totals_by_currency or totals_by_currency
    for currency_code, amount in (total_to_pay_by_currency or {}).items():
        currency = _ascii_safe(str(currency_code).strip().upper()) or "EUR"
        normalized_total_to_pay_by_currency[currency] = Decimal(amount).quantize(Decimal("0.01"))
    summary_currencies = sorted(
        set(effective_totals_by_currency.keys())
        | set(normalized_opening_balance_by_currency.keys())
        | set(normalized_applied_payment_totals_by_currency.keys())
        | set(normalized_total_to_pay_by_currency.keys())
    )
    payment_link_text = _ascii_safe((payment_link_url or "").strip())
    payment_link_preview = ""
    if payment_link_text:
        parsed_link = urlsplit(payment_link_text)
        if parsed_link.scheme and parsed_link.netloc:
            truncated_path = _truncate_text(parsed_link.path or "/", 28)
            payment_link_preview = f"{parsed_link.scheme}://{parsed_link.netloc}{truncated_path}"
        else:
            payment_link_preview = _truncate_text(payment_link_text, 64)
    reserved_adjustment_space = (len(normalized_adjustments) * 18.0) + 34.0 if normalized_adjustments else 0.0
    reserved_payment_details_space = (
        42.0 + (len(normalized_applied_payment_lines) * 18.0)
        if normalized_applied_payment_lines
        else 0.0
    )
    reserved_balance_space = 0.0
    if summary_currencies:
        reserved_balance_space = 24.0 + sum(
            68.0
            if Decimal(normalized_applied_payment_totals_by_currency.get(currency_code, Decimal("0.00"))).quantize(Decimal("0.01"))
            != Decimal("0.00")
            else 54.0
            for currency_code in summary_currencies
        )
    if payment_link_text:
        reserved_balance_space += 52.0
    reserved_balance_space += reserved_payment_details_space
    reserved_note_space = 80.0 if normalized_note else 0.0
    if current_row_top + 140 + reserved_adjustment_space + reserved_balance_space + reserved_note_space > 780:
        pdf.new_page()
        draw_header(include_table_header=False)
        current_row_top = summary_page_row_top

    current_row_top += 20
    pdf.text(x=left, top_y=current_row_top, value=_invoice_text(normalized_language, "totals_title"), size=11, bold=True)
    current_row_top += 16
    pdf.rect(x=left, top_y=current_row_top, width=right - left, height=22.0, stroke_color=(0.82, 0.86, 0.91), fill_color=(0.95, 0.96, 0.98))
    pdf.text(x=col_label_x, top_y=current_row_top + 14, value=_invoice_text(normalized_language, "totals_currency_vat"), size=9, bold=True)
    pdf.text_right(right_x=totals_col_ht_right, top_y=current_row_top + 14, value=_invoice_text(normalized_language, "table_ht"), size=9, bold=True)
    pdf.text_right(right_x=totals_col_vat_right, top_y=current_row_top + 14, value=_invoice_text(normalized_language, "table_vat"), size=9, bold=True)
    pdf.text_right(right_x=totals_col_ttc_right, top_y=current_row_top + 14, value=_invoice_text(normalized_language, "table_ttc"), size=9, bold=True)
    current_row_top += 22

    if totals_by_currency_and_vat_rate:
        for currency_code in sorted(totals_by_currency_and_vat_rate.keys()):
            for vat_rate in sorted(totals_by_currency_and_vat_rate[currency_code].keys()):
                totals = totals_by_currency_and_vat_rate[currency_code][vat_rate]
                pdf.rect(x=left, top_y=current_row_top, width=right - left, height=22.0, stroke_color=(0.90, 0.92, 0.95))
                pdf.text(
                    x=col_label_x,
                    top_y=current_row_top + 14,
                    value=f"{currency_code.upper()} - {vat_rate.quantize(Decimal('0.01'))}%",
                    size=10,
                    bold=True,
                )
                pdf.text_right(
                    right_x=totals_col_ht_right,
                    top_y=current_row_top + 14,
                    value=_format_amount(Decimal(totals["amount_excl_vat"])),
                    size=10,
                    bold=True,
                )
                pdf.text_right(
                    right_x=totals_col_vat_right,
                    top_y=current_row_top + 14,
                    value=_format_amount(Decimal(totals["vat_amount"])),
                    size=10,
                    bold=True,
                )
                pdf.text_right(
                    right_x=totals_col_ttc_right,
                    top_y=current_row_top + 14,
                    value=_format_amount(Decimal(totals["total_incl_vat"])),
                    size=10,
                    bold=True,
                )
                current_row_top += 22
    else:
        for currency_code in sorted(effective_totals_by_currency.keys()):
            totals = effective_totals_by_currency[currency_code]
            pdf.rect(x=left, top_y=current_row_top, width=right - left, height=22.0, stroke_color=(0.90, 0.92, 0.95))
            pdf.text(x=col_label_x, top_y=current_row_top + 14, value=currency_code.upper(), size=10, bold=True)
            pdf.text_right(
                right_x=totals_col_ht_right,
                top_y=current_row_top + 14,
                value=_format_amount(Decimal(totals["amount_excl_vat"])),
                size=10,
                bold=True,
            )
            pdf.text_right(
                right_x=totals_col_vat_right,
                top_y=current_row_top + 14,
                value=_format_amount(Decimal(totals["vat_amount"])),
                size=10,
                bold=True,
            )
            pdf.text_right(
                right_x=totals_col_ttc_right,
                top_y=current_row_top + 14,
                value=_format_amount(Decimal(totals["total_incl_vat"])),
                size=10,
                bold=True,
            )
            current_row_top += 22

    if summary_currencies:
        current_row_top += 14.0
        pdf.text(x=left, top_y=current_row_top, value=_invoice_text(normalized_language, "balance_title"), size=10, bold=True)
        current_row_top += 14.0
        for currency_code in summary_currencies:
            opening_amount = Decimal(normalized_opening_balance_by_currency.get(currency_code, Decimal("0.00"))).quantize(Decimal("0.01"))
            applied_payments_amount = Decimal(
                normalized_applied_payment_totals_by_currency.get(currency_code, Decimal("0.00"))
            ).quantize(Decimal("0.01"))
            period_totals = effective_totals_by_currency.get(currency_code)
            period_amount = (
                Decimal(period_totals["total_incl_vat"]).quantize(Decimal("0.01"))
                if period_totals is not None
                else Decimal("0.00")
            )
            total_to_pay_amount = Decimal(
                normalized_total_to_pay_by_currency.get(currency_code, period_amount)
            ).quantize(Decimal("0.01"))
            opening_label = (
                _invoice_text(normalized_language, "opening_balance_at", date=period_start_label)
                if period_start_label
                else _invoice_text(normalized_language, "opening_balance")
            )
            show_opening_balance = opening_amount != Decimal("0.00") or applied_payments_amount == Decimal("0.00")
            if show_opening_balance:
                pdf.text(x=col_label_x, top_y=current_row_top, value=opening_label, size=9)
                pdf.text_right(
                    right_x=totals_col_ttc_right,
                    top_y=current_row_top,
                    value=f"{_format_amount(opening_amount)} {currency_code}",
                    size=9,
                )
                current_row_top += 14.0
            pdf.text(
                x=col_label_x,
                top_y=current_row_top,
                value=_invoice_text(normalized_language, "period_amount", currency=currency_code),
                size=9,
            )
            pdf.text_right(
                right_x=totals_col_ttc_right,
                top_y=current_row_top,
                value=f"{_format_amount(period_amount)} {currency_code}",
                size=9,
            )
            current_row_top += 14.0
            if applied_payments_amount != Decimal("0.00"):
                pdf.text(
                    x=col_label_x,
                    top_y=current_row_top,
                    value=_invoice_text(normalized_language, "applied_payments", currency=currency_code),
                    size=9,
                )
                pdf.text_right(
                    right_x=totals_col_ttc_right,
                    top_y=current_row_top,
                    value=f"{_format_amount(applied_payments_amount)} {currency_code}",
                    size=9,
                )
                current_row_top += 14.0
            pdf.text(
                x=col_label_x,
                top_y=current_row_top,
                value=_invoice_text(normalized_language, "total_to_pay", currency=currency_code),
                size=10,
                bold=True,
            )
            pdf.text_right(
                right_x=totals_col_ttc_right,
                top_y=current_row_top,
                value=f"{_format_amount(total_to_pay_amount)} {currency_code}",
                size=10,
                bold=True,
                color=(0.18, 0.59, 0.82),
            )
            current_row_top += 26.0

    def ensure_summary_space(required_height: float) -> None:
        nonlocal current_row_top
        if current_row_top + required_height <= 780.0:
            return
        pdf.new_page()
        draw_header(include_table_header=False)
        current_row_top = summary_page_row_top

    def draw_payment_details_header() -> None:
        nonlocal current_row_top
        pdf.text(
            x=left,
            top_y=current_row_top,
            value=_invoice_text(normalized_language, "applied_payment_details_title"),
            size=9,
            bold=True,
        )
        current_row_top += 12.0
        pdf.rect(
            x=left,
            top_y=current_row_top,
            width=right - left,
            height=18.0,
            stroke_color=(0.82, 0.86, 0.91),
            fill_color=(0.95, 0.96, 0.98),
        )
        pdf.text(x=col_date_x, top_y=current_row_top + 12.0, value=_invoice_text(normalized_language, "payment_table_date"), size=8, bold=True)
        pdf.text(x=col_label_x, top_y=current_row_top + 12.0, value=_invoice_text(normalized_language, "payment_table_method"), size=8, bold=True)
        pdf.text(x=left + 220.0, top_y=current_row_top + 12.0, value=_invoice_text(normalized_language, "payment_table_reference"), size=8, bold=True)
        pdf.text_right(right_x=col_ttc_right, top_y=current_row_top + 12.0, value=_invoice_text(normalized_language, "payment_table_amount"), size=8, bold=True)
        current_row_top += 18.0

    if normalized_applied_payment_lines:
        ensure_summary_space(42.0)
        current_row_top += 4.0
        draw_payment_details_header()
        for payment_line in normalized_applied_payment_lines:
            if current_row_top + 18.0 > 780.0:
                pdf.new_page()
                draw_header(include_table_header=False)
                current_row_top = summary_page_row_top
                draw_payment_details_header()
            pdf.rect(x=left, top_y=current_row_top, width=right - left, height=18.0, stroke_color=(0.90, 0.92, 0.95))
            pdf.text(x=col_date_x, top_y=current_row_top + 12.0, value=payment_line.date_label, size=8)
            pdf.text(x=col_label_x, top_y=current_row_top + 12.0, value=payment_line.method_label, size=8)
            pdf.text(x=left + 220.0, top_y=current_row_top + 12.0, value=payment_line.reference_label, size=8)
            pdf.text_right(
                right_x=col_ttc_right,
                top_y=current_row_top + 12.0,
                value=f"{_format_amount(payment_line.amount)} {payment_line.currency}",
                size=8,
                bold=True,
            )
            current_row_top += 18.0
        current_row_top += 8.0

    if payment_link_text:
        ensure_summary_space(52.0)
        pdf.text(
            x=col_label_x,
            top_y=current_row_top,
            value=_invoice_text(normalized_language, "online_payment_title"),
            size=9,
            bold=True,
        )
        current_row_top += 10.0
        button_x = col_label_x
        button_top = current_row_top
        button_width = 118.0
        button_height = 22.0
        pdf.rect(
            x=button_x,
            top_y=button_top,
            width=button_width,
            height=button_height,
            stroke_color=(0.83, 0.69, 0.22),
            fill_color=(0.83, 0.69, 0.22),
            stroke_width=0.8,
        )
        button_label = _invoice_text(normalized_language, "online_payment_button")
        button_text_width = _text_width_estimate(button_label, size=9)
        button_text_x = button_x + max(8.0, (button_width - button_text_width) / 2.0)
        pdf.text(
            x=button_text_x,
            top_y=button_top + 14.0,
            value=button_label,
            size=9,
            bold=True,
            color=(0.11, 0.15, 0.24),
        )
        pdf.add_link(
            x=button_x,
            top_y=button_top,
            width=button_width,
            height=button_height,
            url=payment_link_text,
        )
        current_row_top += button_height + 8.0
        if payment_link_preview:
            pdf.text(x=col_label_x, top_y=current_row_top, value=payment_link_preview, size=8, color=(0.18, 0.59, 0.82))
            current_row_top += 12.0

    if normalized_adjustments:
        if current_row_top + 34.0 + (len(normalized_adjustments) * 18.0) + reserved_note_space > 780:
            pdf.new_page()
            draw_header(include_table_header=False)
            current_row_top = summary_page_row_top
        current_row_top += 16.0
        pdf.text(
            x=left,
            top_y=current_row_top,
            value=_invoice_text(normalized_language, "adjustments_title"),
            size=10,
            bold=True,
        )
        current_row_top += 14.0
        for label, currency, amount in normalized_adjustments:
            pdf.rect(x=left, top_y=current_row_top, width=right - left, height=18.0, stroke_color=(0.90, 0.92, 0.95))
            pdf.text(x=col_label_x, top_y=current_row_top + 12.0, value=label, size=9)
            pdf.text_right(
                right_x=col_ttc_right,
                top_y=current_row_top + 12.0,
                value=f"{_format_amount(amount)} {currency}",
                size=9,
                bold=True,
            )
            current_row_top += 18.0

    if normalized_note:
        note_title_top = 742.0
        note_line_top = note_title_top + 16.0
        max_note_bottom = 810.0
        line_height = 12.0
        max_lines = max(1, int((max_note_bottom - note_line_top) // line_height))
        note_lines = _wrap_text(normalized_note, 100)
        if len(note_lines) > max_lines:
            note_lines = note_lines[:max_lines]
            if note_lines:
                note_lines[-1] = _truncate_text(note_lines[-1], 96) + "..."

        pdf.text(x=left, top_y=note_title_top, value=_invoice_text(normalized_language, "note_title"), size=11, bold=True)
        for index, chunk in enumerate(note_lines):
            pdf.text(x=left, top_y=note_line_top + (index * line_height), value=chunk, size=10)

    normalized_watermark = _ascii_safe((watermark or "").strip())
    if normalized_watermark:
        safe_watermark = _pdf_escape(normalized_watermark.upper()[:24])
        for page_idx in range(len(pdf._pages)):
            pdf._push_on_page(
                page_idx,
                (
                    "q 0.93 0.38 0.38 rg 0.93 0.38 0.38 RG "
                    "BT /F2 84 Tf 1 0 0 1 120.00 320.00 Tm 0.35 0.35 Td "
                    f"({safe_watermark}) Tj ET Q"
                ),
            )

    footer_line_1, footer_line_2 = _company_footer_lines(identity, language=normalized_language)
    for page_idx in range(len(pdf._pages)):
        pdf._push_on_page(
            page_idx,
            f"BT /F1 8.00 Tf 0.420 0.470 0.560 rg 1 0 0 1 {left:.2f} 20.00 Tm ({_pdf_escape(_ascii_safe(footer_line_1))}) Tj ET",
        )
        pdf._push_on_page(
            page_idx,
            f"BT /F1 8.00 Tf 0.420 0.470 0.560 rg 1 0 0 1 {left:.2f} 8.00 Tm ({_pdf_escape(_ascii_safe(footer_line_2))}) Tj ET",
        )

    pdf.add_page_numbers()
    return pdf.build()


def render_payment_receipt_pdf(
    db: Session,
    *,
    receipt_number: str,
    paid_at: datetime,
    client_name: str,
    client_billing_address: str | None,
    amount_paid: Decimal,
    currency: str,
    payment_method: str | None,
    payment_provider: str | None,
    payment_transaction_reference: str | None,
    reservation_label: str,
    scheduled_service_date: date | None,
    location_label: str | None,
    student_name: str | None,
    note: str | None = None,
    legal_entity_id: UUID | None = None,
) -> bytes:
    identity = _company_identity(db, legal_entity_id=legal_entity_id, billing_entity=None)
    pdf = _SimplePdfDocument()
    logo_resource_name: str | None = None
    logo_width = 0.0
    logo_height = 0.0
    if (
        identity.company_logo_jpeg is not None
        and identity.company_logo_width_px is not None
        and identity.company_logo_height_px is not None
    ):
        logo_resource_name = pdf.register_jpeg_image(
            image_bytes=identity.company_logo_jpeg,
            width_px=identity.company_logo_width_px,
            height_px=identity.company_logo_height_px,
        )
        logo_height = 44.0
        logo_width = min(
            150.0,
            logo_height * (identity.company_logo_width_px / max(1, identity.company_logo_height_px)),
        )

    left = 34.0
    right = pdf.width - 34.0

    def draw_header() -> None:
        pdf.rect(
            x=0.0,
            top_y=0.0,
            width=pdf.width,
            height=92.0,
            stroke_color=(0.11, 0.15, 0.24),
            fill_color=(0.11, 0.15, 0.24),
            stroke_width=0.0,
        )
        title_x = left
        if logo_resource_name is not None:
            pdf.draw_image(
                image_name=logo_resource_name,
                x=left,
                top_y=22.0,
                width=logo_width,
                height=logo_height,
            )
            title_x = left + logo_width + 12.0
        pdf.text(x=title_x, top_y=32.0, value=identity.company_name, size=20, bold=True, color=(1, 1, 1))
        pdf.text(x=title_x, top_y=54.0, value="JUSTIFICATIF DE PAIEMENT", size=12, bold=True, color=(0.95, 0.78, 0.48))
        pdf.text_right(
            right_x=right - 2.0,
            top_y=30.0,
            value=_truncate_text(f"Reference: {receipt_number}", 52),
            size=11,
            bold=True,
            color=(1, 1, 1),
        )
        pdf.text_right(
            right_x=right - 2.0,
            top_y=48.0,
            value=f"Paiement recu le: {paid_at.strftime('%d/%m/%Y')}",
            size=10,
            color=(0.92, 0.93, 0.96),
        )

    draw_header()

    issuer_lines = _company_issuer_lines(identity)
    issuer_top_y = 116.0
    for index, line in enumerate(issuer_lines):
        pdf.text(x=left, top_y=issuer_top_y + (index * 16.0), value=line, size=10, bold=index == 0)
    address_top_y = issuer_top_y + (len(issuer_lines) * 16.0)
    for index, chunk in enumerate(_wrap_text(identity.company_address, 48)):
        pdf.text(x=left, top_y=address_top_y + (index * 14.0), value=chunk, size=10)

    recipient_top_y = 116.0
    pdf.text(x=330.0, top_y=recipient_top_y, value="Document pour", size=11, bold=True)
    pdf.text(x=330.0, top_y=recipient_top_y + 18.0, value=client_name, size=10, bold=True)
    billing_address = _ascii_safe((client_billing_address or "").strip()) or "-"
    for index, chunk in enumerate(_wrap_text(billing_address, 34)):
        pdf.text(x=330.0, top_y=recipient_top_y + 34.0 + (index * 14.0), value=chunk, size=10)

    info_box_top = 248.0
    pdf.rect(
        x=left,
        top_y=info_box_top,
        width=right - left,
        height=54.0,
        stroke_color=(0.96, 0.84, 0.71),
        fill_color=(1.0, 0.96, 0.91),
    )
    pdf.text(x=left + 10.0, top_y=info_box_top + 18.0, value="Ce document confirme la reception de votre paiement.", size=11, bold=True)
    pdf.text(
        x=left + 10.0,
        top_y=info_box_top + 34.0,
        value="Le document commercial final de la prestation sera emis a la realisation du service.",
        size=9,
    )

    section_top = 330.0
    pdf.text(x=left, top_y=section_top, value="Paiement", size=11, bold=True)
    payment_rows = [
        ("Montant paye", f"{_format_amount(Decimal(amount_paid).quantize(Decimal('0.01')))} {(_ascii_safe(currency) or 'EUR').upper()}"),
        ("Date de paiement", paid_at.strftime("%d/%m/%Y %H:%M")),
        ("Moyen de paiement", _ascii_safe(payment_method or "") or "-"),
        ("PSP", _ascii_safe(payment_provider or "") or "-"),
        ("Reference transaction", _ascii_safe(payment_transaction_reference or "") or "-"),
    ]
    current_top = section_top + 18.0
    for label, value in payment_rows:
        lines = _wrap_text(value, 52)
        row_height = max(22.0, 12.0 * len(lines) + 8.0)
        pdf.rect(x=left, top_y=current_top, width=right - left, height=row_height, stroke_color=(0.90, 0.92, 0.95))
        pdf.text(x=left + 10.0, top_y=current_top + 14.0, value=label, size=9, bold=True)
        for index, line in enumerate(lines):
            pdf.text(x=260.0, top_y=current_top + 14.0 + (index * 12.0), value=line, size=9)
        current_top += row_height

    current_top += 18.0
    pdf.text(x=left, top_y=current_top, value="Reservation concernee", size=11, bold=True)
    reservation_rows = [
        ("Prestation reservee", _ascii_safe(reservation_label) or "-"),
        (
            "Date prevue de la prestation",
            scheduled_service_date.strftime("%d/%m/%Y") if scheduled_service_date is not None else "-",
        ),
        ("Lieu", _ascii_safe(location_label or "") or "-"),
        ("Beneficiaire / eleve", _ascii_safe(student_name or "") or client_name),
    ]
    current_top += 18.0
    for label, value in reservation_rows:
        lines = _wrap_text(value, 56)
        row_height = max(22.0, 12.0 * len(lines) + 8.0)
        pdf.rect(x=left, top_y=current_top, width=right - left, height=row_height, stroke_color=(0.90, 0.92, 0.95))
        pdf.text(x=left + 10.0, top_y=current_top + 14.0, value=label, size=9, bold=True)
        for index, line in enumerate(lines):
            pdf.text(x=260.0, top_y=current_top + 14.0 + (index * 12.0), value=line, size=9)
        current_top += row_height

    normalized_note = _ascii_safe((note or "").strip())
    if normalized_note:
        current_top += 18.0
        pdf.text(x=left, top_y=current_top, value="Note", size=11, bold=True)
        current_top += 16.0
        for index, line in enumerate(_wrap_text(normalized_note, 96)[:5]):
            pdf.text(x=left, top_y=current_top + (index * 12.0), value=line, size=9)

    footer_line_1, footer_line_2 = _company_footer_lines(identity)
    for page_idx in range(len(pdf._pages)):
        pdf._push_on_page(
            page_idx,
            f"BT /F1 8.00 Tf 0.420 0.470 0.560 rg 1 0 0 1 {left:.2f} 20.00 Tm ({_pdf_escape(_ascii_safe(footer_line_1))}) Tj ET",
        )
        pdf._push_on_page(
            page_idx,
            f"BT /F1 8.00 Tf 0.420 0.470 0.560 rg 1 0 0 1 {left:.2f} 8.00 Tm ({_pdf_escape(_ascii_safe(footer_line_2))}) Tj ET",
        )
    pdf.add_page_numbers()
    return pdf.build()
