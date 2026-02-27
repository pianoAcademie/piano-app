from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting

INVOICE_TEMPLATE_SETTING_KEY = "config_invoice_template_text_v1"
INVOICE_NUMBER_FORMAT_SETTING_KEY = "config_invoice_number_format_v1"
INVOICE_NUMBER_NEXT_SETTING_KEY = "config_invoice_number_next_v1"
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
) -> str:
    template, _ = get_invoice_template(db)
    company_name = _setting_value(db, "config_account_club_name", "Piano Academie")
    company_email = _setting_value(db, "config_account_contact_email", "")
    address_parts = [
        _setting_value(db, "config_account_address_line", ""),
        _setting_value(db, "config_account_postal_code", ""),
        _setting_value(db, "config_account_city", ""),
        _setting_value(db, "config_account_country", ""),
    ]
    company_address = " ".join(part for part in address_parts if part).strip() or "-"

    refund_info = ""
    if refunded_at is not None:
        reason = refund_reason or "-"
        refund_info = f"Rembourse le: {refunded_at.strftime('%d/%m/%Y %H:%M')} | Motif: {reason}"

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
        "company_name": company_name,
        "company_email": company_email or "-",
        "company_address": company_address,
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


class _SimplePdfDocument:
    width = 595.0
    height = 842.0

    def __init__(self) -> None:
        self._pages: list[list[str]] = []
        self.new_page()

    def new_page(self) -> None:
        self._pages.append([])

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

        page_ids: list[int] = []
        next_id = 5
        for page_ops in self._pages:
            content_id = next_id
            page_id = next_id + 1
            next_id += 2
            stream_data = ("\n".join(page_ops) + "\n").encode("latin-1", "replace")
            object_map[content_id] = (
                b"<< /Length " + str(len(stream_data)).encode("ascii") + b" >>\nstream\n" + stream_data + b"endstream"
            )
            object_map[page_id] = (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                + b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
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


def _truncate_text(value: str, max_chars: int) -> str:
    safe = _ascii_safe(value)
    if len(safe) <= max_chars:
        return safe
    if max_chars <= 3:
        return safe[:max_chars]
    return safe[: max_chars - 3].rstrip() + "..."


@dataclass(frozen=True)
class CompanyIdentity:
    company_name: str
    company_email: str
    company_phone: str
    company_siret: str
    company_address: str


def _company_identity(db: Session) -> CompanyIdentity:
    company_name = _setting_value(db, "config_account_club_name", "") or _setting_value(
        db, "config_account_company_name", "Piano Academie"
    )
    company_email = _setting_value(db, "config_account_contact_email", "") or "-"
    company_phone = _setting_value(db, "config_account_contact_phone", "") or "-"
    company_siret = _setting_value(db, "config_account_siret", "") or "-"
    address_parts = [
        _setting_value(db, "config_account_address_line", ""),
        _setting_value(db, "config_account_postal_code", ""),
        _setting_value(db, "config_account_city", ""),
        _setting_value(db, "config_account_country", ""),
    ]
    company_address = " ".join(part for part in address_parts if part).strip() or "-"
    return CompanyIdentity(
        company_name=company_name,
        company_email=company_email,
        company_phone=company_phone,
        company_siret=company_siret,
        company_address=company_address,
    )


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
    note: str | None,
    client_billing_address: str | None = None,
) -> bytes:
    identity = _company_identity(db)
    pdf = _SimplePdfDocument()

    left = 34.0
    right = pdf.width - 34.0
    table_top = 268.0
    row_top = table_top + 22.0

    col_date_x = left + 6
    col_type_x = left + 72
    col_label_x = left + 136
    col_qty_right = left + 334
    col_ht_right = left + 394
    col_vat_rate_right = left + 438
    col_vat_right = left + 486
    col_ttc_right = right - 6

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
        pdf.text(x=left, top_y=34.0, value=identity.company_name, size=20, bold=True, color=(1, 1, 1))
        pdf.text(x=left, top_y=54.0, value="FACTURE", size=12, bold=True, color=(0.95, 0.78, 0.48))
        pdf.text_right(
            right_x=right - 2.0,
            top_y=30.0,
            value=_truncate_text(f"Numero: {invoice_number}", 54),
            size=11,
            bold=True,
            color=(1, 1, 1),
        )
        pdf.text_right(
            right_x=right - 2.0,
            top_y=48.0,
            value=f"Date: {issued_at.strftime('%d/%m/%Y %H:%M')}",
            size=10,
            color=(0.92, 0.93, 0.96),
        )
        pdf.text_right(
            right_x=right - 2.0,
            top_y=66.0,
            value=_truncate_text(f"Client: {client_name}", 54),
            size=10,
            color=(0.92, 0.93, 0.96),
        )
        pdf.text_right(
            right_x=right - 2.0,
            top_y=82.0,
            value=_truncate_text(f"ID client: {client_id}", 54),
            size=9,
            color=(0.82, 0.86, 0.91),
        )

        # Bloc societe emettrice
        pdf.text(x=left, top_y=116.0, value="Societe emettrice", size=11, bold=True)
        pdf.text(x=left, top_y=134.0, value=identity.company_name, size=10, bold=True)
        pdf.text(x=left, top_y=150.0, value=f"SIRET: {identity.company_siret}", size=10)
        pdf.text(x=left, top_y=166.0, value=f"Telephone: {identity.company_phone}", size=10)
        pdf.text(x=left, top_y=182.0, value=f"Email: {identity.company_email}", size=10)
        for index, chunk in enumerate(_wrap_text(identity.company_address, 48)):
            pdf.text(x=left, top_y=198.0 + (index * 14.0), value=chunk, size=10)

        # Bloc client facture
        billing_address = _ascii_safe((client_billing_address or "").strip()) or "-"
        pdf.text(x=330.0, top_y=116.0, value="Facture pour", size=11, bold=True)
        pdf.text(x=330.0, top_y=134.0, value=client_name, size=10, bold=True)
        for index, chunk in enumerate(_wrap_text(billing_address, 34)):
            pdf.text(x=330.0, top_y=150.0 + (index * 14.0), value=chunk, size=10)
        pdf.text(x=330.0, top_y=196.0, value=f"Periode facturee: {period_label}", size=10, bold=True)

        pdf.rect(
            x=left,
            top_y=table_top,
            width=right - left,
            height=22.0,
            stroke_color=(0.82, 0.86, 0.91),
            fill_color=(0.95, 0.96, 0.98),
        )
        pdf.text(x=col_date_x, top_y=282.0, value="Date", size=9, bold=True)
        pdf.text(x=col_type_x, top_y=282.0, value="Type", size=9, bold=True)
        pdf.text(x=col_label_x, top_y=282.0, value="Prestation", size=9, bold=True)
        pdf.text_right(right_x=col_qty_right, top_y=282.0, value="Qt", size=9, bold=True)
        pdf.text_right(right_x=col_ht_right, top_y=282.0, value="HT", size=9, bold=True)
        pdf.text_right(right_x=col_vat_rate_right, top_y=282.0, value="TVA%", size=9, bold=True)
        pdf.text_right(right_x=col_vat_right, top_y=282.0, value="TVA", size=9, bold=True)
        pdf.text_right(right_x=col_ttc_right, top_y=282.0, value="TTC", size=9, bold=True)

    def draw_table_header_for_new_page() -> float:
        draw_header()
        return row_top

    current_row_top = draw_table_header_for_new_page()
    for row in lines:
        label_lines = _wrap_text(row.label, 32)
        row_height = max(20.0, (len(label_lines) * 12.0) + 8.0)
        if current_row_top + row_height > 760.0:
            pdf.new_page()
            current_row_top = draw_table_header_for_new_page()

        pdf.rect(x=left, top_y=current_row_top, width=right - left, height=row_height, stroke_color=(0.90, 0.92, 0.95))
        pdf.text(x=col_date_x, top_y=current_row_top + 14, value=row.date_label, size=9)
        pdf.text(x=col_type_x, top_y=current_row_top + 14, value=row.type_label, size=9)
        for idx, chunk in enumerate(label_lines):
            pdf.text(x=col_label_x, top_y=current_row_top + 14 + (idx * 12), value=chunk, size=9)
        pdf.text_right(right_x=col_qty_right, top_y=current_row_top + 14, value=str(row.quantity), size=9)
        pdf.text_right(right_x=col_ht_right, top_y=current_row_top + 14, value=_format_amount(row.amount_excl_vat), size=9)
        pdf.text_right(right_x=col_vat_rate_right, top_y=current_row_top + 14, value=f"{Decimal(row.vat_rate).quantize(Decimal('0.01'))}%", size=9)
        pdf.text_right(right_x=col_vat_right, top_y=current_row_top + 14, value=_format_amount(row.vat_amount), size=9)
        pdf.text_right(
            right_x=col_ttc_right,
            top_y=current_row_top + 14,
            value=f"{_format_amount(row.total_incl_vat)} {row.currency.upper()}",
            size=9,
            bold=True,
        )
        current_row_top += row_height

    if current_row_top + 140 > 780:
        pdf.new_page()
        draw_header()
        current_row_top = 140.0

    current_row_top += 20
    pdf.text(x=left, top_y=current_row_top, value="Totaux", size=11, bold=True)
    current_row_top += 16
    pdf.rect(x=left, top_y=current_row_top, width=right - left, height=22.0, stroke_color=(0.82, 0.86, 0.91), fill_color=(0.95, 0.96, 0.98))
    pdf.text(x=col_type_x, top_y=current_row_top + 14, value="Devise", size=9, bold=True)
    pdf.text_right(right_x=col_ht_right, top_y=current_row_top + 14, value="HT", size=9, bold=True)
    pdf.text_right(right_x=col_vat_right, top_y=current_row_top + 14, value="TVA", size=9, bold=True)
    pdf.text_right(right_x=col_ttc_right, top_y=current_row_top + 14, value="TTC", size=9, bold=True)
    current_row_top += 22

    for currency_code in sorted(totals_by_currency.keys()):
        totals = totals_by_currency[currency_code]
        pdf.rect(x=left, top_y=current_row_top, width=right - left, height=22.0, stroke_color=(0.90, 0.92, 0.95))
        pdf.text(x=col_type_x, top_y=current_row_top + 14, value=currency_code.upper(), size=10, bold=True)
        pdf.text_right(
            right_x=col_ht_right,
            top_y=current_row_top + 14,
            value=_format_amount(Decimal(totals["amount_excl_vat"])),
            size=10,
            bold=True,
        )
        pdf.text_right(
            right_x=col_vat_right,
            top_y=current_row_top + 14,
            value=_format_amount(Decimal(totals["vat_amount"])),
            size=10,
            bold=True,
        )
        pdf.text_right(
            right_x=col_ttc_right,
            top_y=current_row_top + 14,
            value=_format_amount(Decimal(totals["total_incl_vat"])),
            size=10,
            bold=True,
        )
        current_row_top += 22

    normalized_note = _ascii_safe((note or "").strip())
    if normalized_note:
        current_row_top += 10
        pdf.text(x=left, top_y=current_row_top, value="Note", size=11, bold=True)
        current_row_top += 16
        for chunk in _wrap_text(normalized_note, 100):
            pdf.text(x=left, top_y=current_row_top, value=chunk, size=10)
            current_row_top += 13

    footer_line_1 = f"{identity.company_name} | SIRET: {identity.company_siret} | Tel: {identity.company_phone}"
    footer_line_2 = f"{identity.company_email} | {identity.company_address}"
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
