from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting

INVOICE_TEMPLATE_SETTING_KEY = "config_invoice_template_text_v1"
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


def _wrap_text(value: str, max_chars: int) -> list[str]:
    words = _ascii_safe(value).split()
    if not words:
        return [""]
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


def _company_identity(db: Session) -> tuple[str, str, str]:
    company_name = _setting_value(db, "config_account_club_name", "Piano Academie")
    company_email = _setting_value(db, "config_account_contact_email", "") or "-"
    address_parts = [
        _setting_value(db, "config_account_address_line", ""),
        _setting_value(db, "config_account_postal_code", ""),
        _setting_value(db, "config_account_city", ""),
        _setting_value(db, "config_account_country", ""),
    ]
    company_address = " ".join(part for part in address_parts if part).strip() or "-"
    return company_name, company_email, company_address


def render_invoice_period_pdf(
    db: Session,
    *,
    invoice_number: str,
    issued_at: datetime,
    client_id: str,
    client_name: str,
    period_label: str,
    layout_label: str,
    include_pending: bool,
    include_cancelled: bool,
    lines: list[InvoicePeriodLine],
    totals_by_currency: dict[str, dict[str, Decimal]],
    note: str | None,
) -> bytes:
    company_name, company_email, company_address = _company_identity(db)
    pdf = _SimplePdfDocument()

    left = 36.0
    right = pdf.width - 36.0
    table_top = 252.0
    row_top = table_top + 22.0

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
        pdf.text(x=left, top_y=34.0, value=company_name, size=20, bold=True, color=(1, 1, 1))
        pdf.text(x=left, top_y=54.0, value="FACTURE", size=12, bold=True, color=(0.95, 0.78, 0.48))
        pdf.text(x=pdf.width - 220, top_y=30.0, value=f"Numero: {invoice_number}", size=10, bold=True, color=(1, 1, 1))
        pdf.text(
            x=pdf.width - 220,
            top_y=48.0,
            value=f"Date: {issued_at.strftime('%d/%m/%Y %H:%M')}",
            size=10,
            color=(0.92, 0.93, 0.96),
        )
        pdf.text(x=pdf.width - 220, top_y=66.0, value=f"Client: {client_name}", size=10, color=(0.92, 0.93, 0.96))
        pdf.text(x=pdf.width - 220, top_y=82.0, value=f"ID: {client_id}", size=9, color=(0.82, 0.86, 0.91))

        pdf.text(x=left, top_y=118.0, value=f"Periode facturee: {period_label}", size=10, bold=True)
        pdf.text(x=left, top_y=136.0, value=f"Mode: {layout_label}", size=10)
        pdf.text(
            x=left,
            top_y=154.0,
            value=f"Filtres: en attente={'oui' if include_pending else 'non'} | annule={'oui' if include_cancelled else 'non'}",
            size=10,
        )
        pdf.text(x=left, top_y=176.0, value=company_email, size=10)
        pdf.text(x=left, top_y=194.0, value=company_address, size=10)

        pdf.rect(
            x=left,
            top_y=table_top,
            width=right - left,
            height=22.0,
            stroke_color=(0.82, 0.86, 0.91),
            fill_color=(0.95, 0.96, 0.98),
        )
        pdf.text(x=left + 6, top_y=266.0, value="Date", size=9, bold=True)
        pdf.text(x=left + 86, top_y=266.0, value="Type", size=9, bold=True)
        pdf.text(x=left + 156, top_y=266.0, value="Prestation", size=9, bold=True)
        pdf.text(x=left + 405, top_y=266.0, value="Qt", size=9, bold=True)
        pdf.text(x=left + 445, top_y=266.0, value="TVA", size=9, bold=True)
        pdf.text(x=left + 500, top_y=266.0, value="TTC", size=9, bold=True)

    def draw_table_header_for_new_page() -> float:
        draw_header()
        return row_top

    current_row_top = draw_table_header_for_new_page()
    for line in lines:
        label_lines = _wrap_text(line.label, 44)
        row_height = max(20.0, (len(label_lines) * 12.0) + 8.0)
        if current_row_top + row_height > 760.0:
            pdf.new_page()
            current_row_top = draw_table_header_for_new_page()

        pdf.rect(x=left, top_y=current_row_top, width=right - left, height=row_height, stroke_color=(0.90, 0.92, 0.95))
        pdf.text(x=left + 6, top_y=current_row_top + 14, value=line.date_label, size=9)
        pdf.text(x=left + 86, top_y=current_row_top + 14, value=line.type_label, size=9)
        for idx, chunk in enumerate(label_lines):
            pdf.text(x=left + 156, top_y=current_row_top + 14 + (idx * 12), value=chunk, size=9)
        pdf.text(x=left + 408, top_y=current_row_top + 14, value=str(line.quantity), size=9)
        pdf.text(x=left + 445, top_y=current_row_top + 14, value=_format_amount(line.vat_amount), size=9)
        pdf.text(
            x=left + 500,
            top_y=current_row_top + 14,
            value=f"{_format_amount(line.total_incl_vat)} {line.currency.upper()}",
            size=9,
            bold=True,
        )
        current_row_top += row_height

    if current_row_top + 140 > 780:
        pdf.new_page()
        current_row_top = 110.0

    current_row_top += 18
    pdf.text(x=left, top_y=current_row_top, value="Totaux", size=11, bold=True)
    current_row_top += 18
    for currency_code in sorted(totals_by_currency.keys()):
        totals = totals_by_currency[currency_code]
        pdf.text(
            x=left,
            top_y=current_row_top,
            value=(
                f"{currency_code.upper()}  HT {_format_amount(totals['amount_excl_vat'])}  "
                + f"TVA {_format_amount(totals['vat_amount'])}  TTC {_format_amount(totals['total_incl_vat'])}"
            ),
            size=10,
            bold=True,
        )
        current_row_top += 16

    normalized_note = _ascii_safe((note or "").strip())
    if normalized_note:
        current_row_top += 8
        pdf.text(x=left, top_y=current_row_top, value="Note", size=11, bold=True)
        current_row_top += 16
        for chunk in _wrap_text(normalized_note, 100):
            pdf.text(x=left, top_y=current_row_top, value=chunk, size=10)
            current_row_top += 13

    pdf.text(x=left, top_y=806, value=company_name, size=9, bold=True, color=(0.40, 0.45, 0.54))
    pdf.text(x=left, top_y=822, value=f"{company_email} | {company_address}", size=8, color=(0.45, 0.50, 0.58))
    return pdf.build()
