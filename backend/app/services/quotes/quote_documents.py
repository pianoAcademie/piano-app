from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal
from html import escape, unescape as html_unescape
import io
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting
from app.models.quote import Prospect, Quote, QuoteLine, QuoteTemplateVersion, TermsTemplateVersion
from app.models.user import User


AUDIENCE_ADMIN_PREVIEW = "admin_preview"
AUDIENCE_PUBLIC_PAGE = "public_page"
AUDIENCE_CLIENT_PDF = "client_pdf"
DEFAULT_AUDIENCE = AUDIENCE_CLIENT_PDF
ACCOUNT_LOGO_SETTING_KEY = "config_account_logo_data_url"


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "oui"}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _decimal_str(value: Decimal) -> str:
    amount = Decimal(value or Decimal("0")).quantize(Decimal("0.01"))
    return f"{amount:.2f}".replace(".", ",")


def _decimal_from_any(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception:
        return default
    if not parsed.is_finite():
        return default
    return parsed


def _split_ttc_with_rate(total_ttc: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    ttc_amount = Decimal(total_ttc or Decimal("0")).quantize(Decimal("0.01"))
    rate = Decimal(vat_rate or Decimal("0")).quantize(Decimal("0.01"))
    if rate <= Decimal("0.00"):
        return ttc_amount, Decimal("0.00")
    divisor = Decimal("1.00") + (rate / Decimal("100"))
    if divisor <= Decimal("0.00"):
        return ttc_amount, Decimal("0.00")
    ht_amount = (ttc_amount / divisor).quantize(Decimal("0.01"))
    vat_amount = (ttc_amount - ht_amount).quantize(Decimal("0.01"))
    return ht_amount, vat_amount


def _money(value: Decimal, currency: str) -> str:
    return f"{_decimal_str(value)} {currency}"


def _schedule_due_label(item: dict[str, Any]) -> str:
    due_type = str(item.get("due_type") or "").strip().lower()
    due_label = str(item.get("due_label") or "").strip()
    normalized = due_label.lower()
    if due_type == "on_registration":
        return "à réception de votre facture"
    if normalized in {
        "a reception",
        "a reception du dossier",
        "a reception de votre facture",
        "à reception",
        "à reception du dossier",
        "à reception de votre facture",
        "à réception",
        "à réception du dossier",
        "à réception de votre facture",
    }:
        return "à réception de votre facture"
    if due_label:
        return due_label
    return due_type or "-"


def _name(first_name: str | None, last_name: str | None, fallback: str = "-") -> str:
    value = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
    return value or fallback


def _date_label(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y")


def _datetime_label(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M")


def _birth_date_label(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, date_format).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw


def _document_style_html() -> str:
    return (
        "<style>"
        "body{font-family:Arial,Helvetica,sans-serif;color:#1f1f1f;font-size:11px;line-height:1.4;}"
        "h1,h2,h3{color:#111827;margin:0 0 8px 0;page-break-after:avoid;}"
        "p{margin:0 0 8px 0;}"
        ".quote-muted{color:#5b6470;}"
        ".quote-page-break{page-break-before:always;}"
        ".quote-block{border:1px solid #d4dae3;background:#fbfcfe;padding:10px;margin:0 0 10px 0;page-break-inside:auto;}"
        ".quote-identity-grid{display:block;width:100%;}"
        ".quote-identity-card{border:1px solid #d3dbe7;background:#ffffff;padding:10px 12px;margin:0 0 10px 0;page-break-inside:avoid;}"
        ".quote-identity-card h3{margin:0 0 8px 0;font-size:13px;color:#111827;}"
        ".quote-identity-meta{width:100%;border-collapse:collapse;font-size:11px;}"
        ".quote-identity-meta td{padding:6px 8px;border-bottom:1px solid #edf2f7;vertical-align:top;}"
        ".quote-identity-meta tr:last-child td{border-bottom:none;}"
        ".quote-identity-meta td:first-child{width:36%;font-weight:700;color:#1f2937;background:#f8fafc;}"
        ".quote-header{width:100%;border-collapse:collapse;margin:0 0 10px 0;}"
        ".quote-header td{vertical-align:top;}"
        ".quote-brand-logo{display:inline-block;min-width:84px;padding:7px 9px;background:#111111;color:#d2b04c;font-size:10px;line-height:1.2;font-weight:700;letter-spacing:0.5px;text-align:center;}"
        ".quote-brand-logo-img{display:inline-block;max-width:140px;max-height:70px;object-fit:contain;}"
        ".quote-cover{text-align:center;min-height:220mm;padding-top:30mm;}"
        ".quote-cover-title{font-size:28px;letter-spacing:0.3px;text-transform:uppercase;margin-bottom:6mm;}"
        ".quote-cover-subtitle{font-size:14px;color:#4b5563;margin-bottom:9mm;}"
        ".quote-cover-name{font-size:22px;margin-bottom:4mm;}"
        ".quote-cover-meta{font-size:12px;color:#4b5563;line-height:1.6;}"
        ".quote-table{width:100%;border-collapse:collapse;border-spacing:0;margin:6px 0 10px 0;font-size:11px;table-layout:auto;}"
        ".quote-table thead{display:table-header-group;}"
        ".quote-table tfoot{display:table-footer-group;}"
        ".quote-table tr{page-break-inside:avoid;}"
        ".quote-table th{background:#e7edf7 !important;color:#111827 !important;border:1px solid #c2ccda !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;text-align:left !important;font-weight:700 !important;line-height:1.4 !important;vertical-align:middle !important;height:auto !important;min-height:30px;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;}"
        ".quote-table td{border:1px solid #d3dbe7 !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;vertical-align:middle !important;color:#111827 !important;line-height:1.45 !important;height:auto !important;min-height:30px;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;}"
        ".quote-table td>*{margin-top:0;margin-bottom:0;}"
        ".quote-footer{width:100%;border-collapse:collapse;margin-top:12px;padding-top:8px;border-top:1px solid #cdd4de;font-size:10px;color:#475467;}"
        ".quote-footer td{vertical-align:top;}"
        ".quote-terms-title{margin-top:0;}"
        "</style>"
    )


def _account_logo_data_url(*, db: Session | None) -> str:
    if db is None:
        return ""
    row = db.scalar(select(AppSetting).where(AppSetting.key == ACCOUNT_LOGO_SETTING_KEY))
    if row is None:
        return ""
    value = str(row.value or "").strip()
    if not value.lower().startswith("data:image/"):
        return ""
    return value


def _brand_logo_html(*, db: Session | None, variant: str = "header") -> str:
    logo_data_url = _account_logo_data_url(db=db)
    if logo_data_url:
        width_px = "118" if variant == "cover" else "86"
        return (
            "<img "
            "class='quote-brand-logo-img' "
            f"src='{escape(logo_data_url)}' "
            f"width='{width_px}' "
            "style='display:block;width:auto;height:auto;' "
            "alt='Piano Academie'/>"
        )
    return "<div class='quote-brand-logo'>PIANO<br/>ACADEMIE</div>"


MONTH_LABELS_FR = (
    "Janvier",
    "Fevrier",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Aout",
    "Septembre",
    "Octobre",
    "Novembre",
    "Decembre",
)


def _session_month_day(value: object) -> tuple[int, int] | None:
    raw = str(value or "").strip()
    parsed = re.match(r"^\d{4}-(\d{2})-(\d{2})$", raw)
    if parsed is None:
        return None
    month = int(parsed.group(1))
    day = int(parsed.group(2))
    if month < 1 or month > 12 or day < 1 or day > 31:
        return None
    return month, day


def _calendar_semester_rows(month_map: dict[int, set[int]], *, semester: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for month in sorted(month_map.keys()):
        if semester == 1 and not (month >= 9 or month <= 1):
            continue
        if semester == 2 and not (2 <= month <= 8):
            continue
        days = sorted(month_map.get(month) or set())
        if not days:
            continue
        rows.append((MONTH_LABELS_FR[month - 1], ", ".join(str(day) for day in days)))
    return rows


def _calendar_visual_summary(sessions: list[dict[str, Any]]) -> tuple[str, int]:
    grouped: dict[str, dict[int, set[int]]] = {}
    for session in sessions:
        parsed = _session_month_day(session.get("date"))
        if parsed is None:
            continue
        month, day = parsed
        activity_label = str(session.get("activity_label") or "").strip() or "Activite"
        location_label = str(session.get("location_label") or "").strip()
        title = f"{activity_label} · {location_label}" if location_label else activity_label
        if title not in grouped:
            grouped[title] = {}
        if month not in grouped[title]:
            grouped[title][month] = set()
        grouped[title][month].add(day)

    if not grouped:
        return "<p>Aucune seance planifiee.</p>", 0

    blocks: list[str] = []
    for index, title in enumerate(sorted(grouped.keys()), start=1):
        month_map = grouped[title]
        count = sum(len(values) for values in month_map.values())
        sem1 = _calendar_semester_rows(month_map, semester=1)
        sem2 = _calendar_semester_rows(month_map, semester=2)

        semester_rows: list[tuple[str, str, str]] = []
        for month_label, days in sem1:
            semester_rows.append(("1er semestre", month_label, days))
        for month_label, days in sem2:
            semester_rows.append(("2e semestre", month_label, days))
        if not semester_rows:
            semester_rows.append(("-", "-", "Aucune seance"))
        semesters_html = "".join(
            "<tr>"
            f"<td valign='middle' style='border:1px solid #d8dee7;padding:10px;vertical-align:middle;'>{escape(semester)}</td>"
            f"<td valign='middle' style='border:1px solid #d8dee7;padding:10px;vertical-align:middle;'><strong>{escape(month_label)}</strong></td>"
            f"<td valign='top' style='border:1px solid #d8dee7;padding:10px;vertical-align:top;'>{escape(days)}</td>"
            "</tr>"
            for semester, month_label, days in semester_rows
        )

        separator_html = (
            "<div style='height:8px;margin:6px 0 10px 0;border-top:2px dashed #d8deea;'></div>"
            if index > 1
            else ""
        )
        blocks.append(
            separator_html
            + "<div style='border:2px solid #cfd6e2;padding:0;margin:0 0 22px 0;page-break-inside:auto;background:#ffffff;'>"
            "<div style='background:#f8fafc;border-bottom:1px solid #d6d9de;padding:8px 10px;font-weight:700;color:#0f172a;'>"
            f"Activite {index}"
            "</div>"
            "<div style='padding:8px;'>"
            "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
            "style='width:100%;border-collapse:collapse;border-spacing:0;margin:0 0 8px 0;font-size:11px;'>"
            "<tbody>"
            "<tr>"
            "<td bgcolor='#DDE8FA' "
            "style='background-color:#DDE8FA;color:#111827;border:1px solid #c2ccda;padding:12px 10px;text-align:left;font-weight:700;'>Activite / lieu</td>"
            "<td bgcolor='#DDE8FA' align='right' "
            "style='background-color:#DDE8FA;color:#111827;border:1px solid #c2ccda;padding:12px 10px;text-align:right;font-weight:700;'>Nombre de cours</td>"
            "</tr>"
            f"<tr><td valign='middle' style='border:1px solid #d8dee7;padding:12px 10px;vertical-align:middle;'><strong>{escape(title)}</strong></td><td align='right' valign='middle' style='border:1px solid #d8dee7;padding:12px 10px;vertical-align:middle;'><strong>{count} cours</strong></td></tr>"
            "</tbody>"
            "</table>"
            "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
            "style='width:100%;border-collapse:collapse;border-spacing:0;margin:0;font-size:11px;'>"
            "<tbody>"
            "<tr>"
            "<td bgcolor='#EEF3FC' width='22%' "
            "style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>Semestre</td>"
            "<td bgcolor='#EEF3FC' width='24%' "
            "style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>Mois</td>"
            "<td bgcolor='#EEF3FC' "
            "style='background-color:#EEF3FC;color:#111827;border:1px solid #c2ccda;padding:10px;text-align:left;font-weight:700;'>Dates de cours</td>"
            "</tr>"
            f"{semesters_html}"
            "</tbody>"
            "</table>"
            "</div>"
            "</div>"
        )

    return "".join(blocks), len(grouped)


def _table_html(headers: list[str], rows: list[list[str]], *, empty_label: str) -> str:
    if not rows:
        return f"<p class='quote-muted'>{escape(empty_label)}</p>"
    head = "".join(
        "<th bgcolor='#E7EDF7' "
        "style='background-color:#E7EDF7;color:#111827;border:1px solid #c2ccda;padding:12px 10px 12px 10px;padding-top:12px;padding-right:10px;padding-bottom:12px;padding-left:10px;text-align:left;font-weight:700;line-height:1.4;vertical-align:middle;height:auto;white-space:normal;word-break:break-word;overflow-wrap:anywhere;'>"
        f"{escape(cell)}"
        "</th>"
        for cell in headers
    )
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            + "".join(
                "<td valign='middle' style='border:1px solid #d8dee7;padding:12px 10px 12px 10px;padding-top:12px;padding-right:10px;padding-bottom:12px;padding-left:10px;vertical-align:middle;color:#111827;line-height:1.45;height:auto;white-space:normal;word-break:break-word;overflow-wrap:anywhere;'>"
                f"{escape(cell)}"
                "</td>"
                for cell in row
            )
            + "</tr>"
        )
    body = "".join(body_rows)
    return (
        "<table class='quote-table' border='1' cellspacing='0' cellpadding='10' width='100%' "
        "style='width:100%;border-collapse:collapse;border-spacing:0;margin:6px 0 10px 0;font-size:11px;table-layout:auto;'>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
    )


def _weekday_label(value: Any) -> str:
    labels = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")
    try:
        day = int(value)
    except (TypeError, ValueError):
        return "-"
    if day < 0 or day > 6:
        return "-"
    return labels[day]


def _parse_hhmm_to_minutes(value: Any) -> int | None:
    raw = str(value or "").strip()
    parsed = re.match(r"^(\d{2}):(\d{2})$", raw)
    if parsed is None:
        return None
    hours = int(parsed.group(1))
    minutes = int(parsed.group(2))
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        return None
    return hours * 60 + minutes


def _duration_label(*, start_time: Any, end_time: Any, fallback_minutes: Any) -> str:
    try:
        fallback = int(fallback_minutes)
    except (TypeError, ValueError):
        fallback = 0
    if fallback > 0:
        return f"{fallback} min"
    start_minutes = _parse_hhmm_to_minutes(start_time)
    end_minutes = _parse_hhmm_to_minutes(end_time)
    if start_minutes is None or end_minutes is None:
        return "-"
    delta = end_minutes - start_minutes
    if delta <= 0:
        delta += 24 * 60
    return f"{delta} min"


def _modality_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Cours"
    mapping = {
        "ONLINE": "En ligne",
        "ONSITE": "Presentiel",
        "HYBRID": "Hybride",
    }
    return mapping.get(raw.upper(), raw)


def _planning_blocks_table_html(snapshot: dict[str, Any]) -> str:
    blocks = [item for item in _json_list(snapshot.get("blocks")) if isinstance(item, dict)]
    rows: list[list[str]] = []
    for block in blocks:
        activity_label = str(block.get("activity_label") or "-").strip() or "-"
        activity_type = str(block.get("activity_type_label") or "").strip()
        if not activity_type:
            activity_type = _modality_label(block.get("modality"))
        location_label = str(block.get("location_label") or "-").strip() or "-"
        weekday = str(block.get("weekday_label") or "").strip() or _weekday_label(block.get("weekday"))
        start_time = str(block.get("start_time") or "").strip()
        end_time = str(block.get("end_time") or "").strip()
        time_range = f"{start_time} - {end_time}" if start_time and end_time else "-"
        duration = _duration_label(
            start_time=start_time,
            end_time=end_time,
            fallback_minutes=block.get("duration_minutes"),
        )
        rows.append([activity_type, activity_label, location_label, weekday, time_range, duration])
    return _table_html(
        ["Type activite", "Activite", "Lieu", "Jour", "Horaire", "Duree"],
        rows,
        empty_label="Aucun bloc planning.",
    )


def _is_adjustment_line(line: QuoteLine) -> bool:
    line_type = (line.line_type or "").strip().lower()
    master_item_type = (line.master_item_type or "").strip().lower()
    return line_type in {"discount", "surcharge"} or master_item_type in {"discount_rule", "surcharge_rule"}


def _line_groups(lines: list[QuoteLine]) -> tuple[list[QuoteLine], list[QuoteLine], list[QuoteLine], list[QuoteLine]]:
    services: list[QuoteLine] = []
    products: list[QuoteLine] = []
    kits: list[QuoteLine] = []
    adjustments: list[QuoteLine] = []
    for line in lines:
        if _is_adjustment_line(line):
            adjustments.append(line)
            continue
        if (line.line_category or "").strip().lower() == "service":
            services.append(line)
            continue
        if line.kit_id is not None or (line.master_item_type or "").strip().lower() == "kit":
            kits.append(line)
            continue
        products.append(line)
    return services, products, kits, adjustments


def _load_quote_template_snapshot(*, db: Session | None, quote: Quote) -> tuple[str, str]:
    if db is not None and quote.quote_template_version_id is not None:
        version = db.scalar(select(QuoteTemplateVersion).where(QuoteTemplateVersion.id == quote.quote_template_version_id))
        if version is not None:
            snapshot = version.content_snapshot or {}
            subject = str(snapshot.get("subject_template") or "").strip()
            body = str(snapshot.get("body_template") or "").strip()
            if subject or body:
                return subject, body
    meta = quote.meta or {}
    subject = str(meta.get("template_subject") or "").strip()
    body = str(meta.get("template_body") or "").strip()
    return subject, body


def _load_terms_template_content(*, db: Session | None, quote: Quote) -> tuple[str, str]:
    if db is not None and quote.terms_template_version_id is not None:
        version = db.scalar(select(TermsTemplateVersion).where(TermsTemplateVersion.id == quote.terms_template_version_id))
        if version is not None:
            snapshot = version.content_snapshot or {}
            label = str(snapshot.get("version_label") or "").strip()
            content = str(snapshot.get("content") or "").strip()
            if label or content:
                return label, content
    cgv_snapshot = quote.cgv_snapshot or {}
    return str(cgv_snapshot.get("version_label") or "").strip(), str(cgv_snapshot.get("content") or "").strip()


def _resolve_prospect_data(*, db: Session | None, quote: Quote) -> dict[str, str]:
    values: dict[str, str] = {
        "prospect_type": "adult",
        "prospect_type_label": "Adulte",
        "adult_first_name": "",
        "adult_last_name": "",
        "adult_full_name": "",
        "adult_email": "",
        "adult_phone": "",
        "adult_address": "",
        "parent_first_name": "",
        "parent_last_name": "",
        "parent_full_name": "",
        "parent_email": "",
        "parent_phone": "",
        "parent_address": "",
        "child_first_name": "",
        "child_last_name": "",
        "child_full_name": "",
        "child_birth_date": "",
    }
    if db is None or quote.prospect_id is None:
        return values

    prospect = db.scalar(select(Prospect).where(Prospect.id == quote.prospect_id))
    if prospect is None:
        return values

    meta = prospect.meta or {}
    prospect_type = "child" if str(meta.get("prospect_type") or "").strip().lower() == "child" else "adult"
    values["prospect_type"] = prospect_type
    values["prospect_type_label"] = "Enfant" if prospect_type == "child" else "Adulte"

    if prospect_type == "child":
        child_meta = meta.get("child") if isinstance(meta.get("child"), dict) else {}
        parent_meta = meta.get("parent_referent") if isinstance(meta.get("parent_referent"), dict) else {}
        child_first_name = str((child_meta or {}).get("first_name") or prospect.first_name or "").strip()
        child_last_name = str((child_meta or {}).get("last_name") or prospect.last_name or "").strip()
        values["child_first_name"] = child_first_name
        values["child_last_name"] = child_last_name
        values["child_full_name"] = _name(child_first_name, child_last_name, fallback="")
        values["child_birth_date"] = str((child_meta or {}).get("birth_date") or "").strip()

        parent_first_name = str((parent_meta or {}).get("first_name") or "").strip()
        parent_last_name = str((parent_meta or {}).get("last_name") or "").strip()
        parent_email = str((parent_meta or {}).get("email") or prospect.email or "").strip().lower()
        parent_phone = str((parent_meta or {}).get("phone") or prospect.phone or "").strip()
        parent_address = str((parent_meta or {}).get("address") or "").strip()
        if prospect.parent_prospect_id is not None:
            parent = db.scalar(select(Prospect).where(Prospect.id == prospect.parent_prospect_id))
            if parent is not None:
                parent_first_name = parent.first_name or parent_first_name
                parent_last_name = parent.last_name or parent_last_name
                parent_email = (parent.email or parent_email).strip().lower()
                parent_phone = (parent.phone or parent_phone).strip()
                if not parent_address:
                    parent_meta_data = parent.meta or {}
                    parent_address = str(parent_meta_data.get("adult_address") or "").strip()

        values["parent_first_name"] = parent_first_name
        values["parent_last_name"] = parent_last_name
        values["parent_full_name"] = _name(parent_first_name, parent_last_name, fallback="")
        values["parent_email"] = parent_email
        values["parent_phone"] = parent_phone
        values["parent_address"] = parent_address
    else:
        values["adult_first_name"] = (prospect.first_name or "").strip()
        values["adult_last_name"] = (prospect.last_name or "").strip()
        values["adult_full_name"] = _name(prospect.first_name, prospect.last_name, fallback="")
        values["adult_email"] = (prospect.email or "").strip().lower()
        values["adult_phone"] = (prospect.phone or "").strip()
        values["adult_address"] = str(meta.get("adult_address") or "").strip()

    return values


def _resolve_client_data(*, db: Session | None, quote: Quote) -> dict[str, str]:
    values: dict[str, str] = {
        "client_first_name": "",
        "client_last_name": "",
        "client_full_name": "",
        "client_email": "",
        "client_phone": "",
        "client_address": "",
    }
    if db is None or quote.client_id is None:
        return values
    user = db.scalar(select(User).where(User.id == quote.client_id))
    if user is None:
        return values
    values["client_first_name"] = (user.first_name or "").strip()
    values["client_last_name"] = (user.last_name or "").strip()
    values["client_full_name"] = _name(user.first_name, user.last_name, fallback="")
    values["client_email"] = (user.email or "").strip().lower()
    values["client_phone"] = (user.mobile_phone_1 or user.phone or "").strip()
    values["client_address"] = " ".join(
        part for part in [user.address_line or "", user.postal_code or "", user.city or ""] if part
    ).strip()
    return values


def _resolve_schedule_visibility_by_audience(*, quote: Quote) -> dict[str, bool]:
    default_visibility = {
        AUDIENCE_ADMIN_PREVIEW: True,
        AUDIENCE_PUBLIC_PAGE: False,
        AUDIENCE_CLIENT_PDF: False,
    }
    payment_snapshot = _json_object(quote.payment_terms_snapshot)
    snapshot_visibility = _json_object(payment_snapshot.get("schedule_visibility"))
    if snapshot_visibility:
        return {
            AUDIENCE_ADMIN_PREVIEW: _is_true(
                snapshot_visibility.get(AUDIENCE_ADMIN_PREVIEW, default_visibility[AUDIENCE_ADMIN_PREVIEW])
            ),
            AUDIENCE_PUBLIC_PAGE: _is_true(
                snapshot_visibility.get(AUDIENCE_PUBLIC_PAGE, default_visibility[AUDIENCE_PUBLIC_PAGE])
            ),
            AUDIENCE_CLIENT_PDF: _is_true(
                snapshot_visibility.get(AUDIENCE_CLIENT_PDF, default_visibility[AUDIENCE_CLIENT_PDF])
            ),
        }
    meta = _json_object(quote.meta)
    visibility_root = _json_object(meta.get("document_visibility"))
    raw = _json_object(visibility_root.get("payment_schedule_detailed"))
    if not raw:
        raw = _json_object(meta.get("payment_schedule_visibility"))
    if not raw:
        return default_visibility
    return {
        AUDIENCE_ADMIN_PREVIEW: _is_true(raw.get(AUDIENCE_ADMIN_PREVIEW, default_visibility[AUDIENCE_ADMIN_PREVIEW])),
        AUDIENCE_PUBLIC_PAGE: _is_true(raw.get(AUDIENCE_PUBLIC_PAGE, default_visibility[AUDIENCE_PUBLIC_PAGE])),
        AUDIENCE_CLIENT_PDF: _is_true(raw.get(AUDIENCE_CLIENT_PDF, default_visibility[AUDIENCE_CLIENT_PDF])),
    }


def _resolve_payment_method_label(*, quote: Quote) -> str:
    snapshot = _json_object(quote.payment_terms_snapshot)
    for key in ("payment_method_label", "plan_name", "payment_plan_name", "payment_method"):
        value = str(snapshot.get(key) or "").strip()
        if value:
            return value
    meta = _json_object(quote.meta)
    for key in ("payment_plan_label", "payment_method_label", "payment_method", "payment_plan_name"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return "Paiement non precise"


def _extract_document_context(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> dict[str, Any]:
    prospect_data = _resolve_prospect_data(db=db, quote=quote)
    client_data = _resolve_client_data(db=db, quote=quote)

    schedule = [item for item in _json_list(_json_object(quote.payment_terms_snapshot).get("schedule")) if isinstance(item, dict)]
    has_installment_schedule = len(schedule) > 1
    schedule_visibility = _resolve_schedule_visibility_by_audience(quote=quote)

    calendar_snapshot = _json_object(quote.calendar_snapshot)
    calendar_solfege = _json_object(calendar_snapshot.get("solfege"))
    solfege_selected_slot = _json_object(calendar_solfege.get("selected_slot"))
    selected_solfege_slot = _json_object(quote.selected_solfege_slot)
    if not selected_solfege_slot:
        selected_solfege_slot = solfege_selected_slot

    meta = _json_object(quote.meta)
    activity_solfege = [item for item in _json_list(meta.get("activity_solfege")) if isinstance(item, dict)]
    masterclass_blocks = [item for item in _json_list(meta.get("masterclass_blocks")) if isinstance(item, dict)]
    pass_recup_enabled = _is_true(meta.get("pass_recup_enabled"))

    solfege_enabled = bool(
        quote.estimated_solfege_level
        or quote.solfege_duration_minutes
        or selected_solfege_slot
        or activity_solfege
    )
    masterclass_enabled = bool(masterclass_blocks) or _is_true(meta.get("masterclass_enabled"))

    schedule_allowed_for_audience = bool(schedule_visibility.get(audience, False))
    show_schedule_detailed = has_installment_schedule and schedule_allowed_for_audience
    payment_schedule_compact_notice = ""
    if schedule and not show_schedule_detailed:
        if len(schedule) == 1:
            payment_schedule_compact_notice = f"1 échéance : {_schedule_due_label(schedule[0])}"
        else:
            payment_schedule_compact_notice = (
                f"Paiement en {len(schedule)} échéances. Le détail des échéances est communiqué séparément."
            )
    payment_instruction = str(_json_object(quote.payment_terms_snapshot).get("payment_instruction") or "").strip()

    prospect_type = str(prospect_data.get("prospect_type") or "adult").strip().lower()
    show_child_block = prospect_type == "child"
    show_adult_block = not show_child_block

    display_flags: dict[str, bool] = {
        "showAdultBlock": show_adult_block,
        "showChildBlock": show_child_block,
        "showPaymentMethodBlock": True,
        "showPaymentScheduleDetailed": show_schedule_detailed,
        "showPaymentScheduleCompactNotice": bool(payment_schedule_compact_notice),
        "showSolfegeSection": solfege_enabled,
        "showSolfegeCompactNotice": not solfege_enabled,
        "showMasterclassSection": masterclass_enabled,
        "showMasterclassCompactNotice": not masterclass_enabled,
        "showPassRecupSection": pass_recup_enabled,
        "showPassRecupCompactNotice": not pass_recup_enabled,
    }
    return {
        "audience": audience,
        "prospect_type": prospect_type,
        "schedule": schedule,
        "schedule_visibility": schedule_visibility,
        "payment_method_label": _resolve_payment_method_label(quote=quote),
        "payment_schedule_compact_notice": payment_schedule_compact_notice,
        "payment_instruction": payment_instruction,
        "solfege_enabled": solfege_enabled,
        "solfege_level": str(quote.estimated_solfege_level or "").strip(),
        "solfege_duration_minutes": quote.solfege_duration_minutes,
        "solfege_selected_slot": selected_solfege_slot,
        "masterclass_enabled": masterclass_enabled,
        "masterclass_blocks": masterclass_blocks,
        "pass_recup_enabled": pass_recup_enabled,
        "display_flags": display_flags,
        "prospect_data": prospect_data,
        "client_data": client_data,
    }


def build_quote_document_context(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> dict[str, Any]:
    context = _extract_document_context(db=db, quote=quote, lines=lines, audience=audience)
    visible_blocks: list[str] = []
    hidden_blocks: list[str] = []
    for block_name, flag_key in (
        ("adult_identity", "showAdultBlock"),
        ("child_parent_identity", "showChildBlock"),
        ("payment_method", "showPaymentMethodBlock"),
        ("payment_schedule_detailed", "showPaymentScheduleDetailed"),
        ("payment_schedule_compact_notice", "showPaymentScheduleCompactNotice"),
        ("solfege", "showSolfegeSection"),
        ("solfege_compact_notice", "showSolfegeCompactNotice"),
        ("masterclass", "showMasterclassSection"),
        ("masterclass_compact_notice", "showMasterclassCompactNotice"),
        ("pass_recup", "showPassRecupSection"),
        ("pass_recup_compact_notice", "showPassRecupCompactNotice"),
    ):
        if bool(context["display_flags"].get(flag_key)):
            visible_blocks.append(block_name)
        else:
            hidden_blocks.append(block_name)
    context["visible_blocks"] = visible_blocks
    context["hidden_blocks"] = hidden_blocks
    return context


TOKEN_RE = re.compile(r"\{[\s\xa0]*([a-zA-Z0-9_]+)[\s\xa0]*\}")


def _apply_template(
    template: str,
    *,
    values: dict[str, str],
    html_keys: set[str],
    html_output: bool,
) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        raw_value = values.get(key, "")
        if html_output:
            if key in html_keys:
                return raw_value
            return escape(raw_value)
        return raw_value

    return TOKEN_RE.sub(repl, template)


def _normalize_block_placeholder_wrappers(template: str, *, keys: set[str]) -> str:
    raw = str(template or "")
    if not raw or not keys:
        return raw
    normalized = raw
    for key in keys:
        key_pattern = r"\{[\s\xa0]*" + re.escape(key) + r"[\s\xa0]*\}"
        for tag in ("p", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6"):
            normalized = re.sub(
                rf"<{tag}\b[^>]*>\s*{key_pattern}\s*</{tag}>",
                "{" + key + "}",
                normalized,
                flags=re.IGNORECASE | re.DOTALL,
            )
            normalized = re.sub(
                rf"<{tag}\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*{key_pattern}(?:\s*(?:<br\s*/?>|&nbsp;))*\s*</{tag}>",
                "{" + key + "}",
                normalized,
                flags=re.IGNORECASE | re.DOTALL,
            )
    return normalized


def _as_html_fragment(content: str) -> str:
    normalized = (content or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    if "<" in normalized and ">" in normalized:
        return normalized
    return "<p>" + "<br/>".join(line for line in normalized.split("\n")) + "</p>"


def _cleanup_rendered_block_markup(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    cleaned = raw
    patterns = (
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<div\b.*?</div>)\s*</p>",
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<table\b.*?</table>)\s*</p>",
        r"<p\b[^>]*>\s*(?:<br\s*/?>\s*|&nbsp;\s*)*(<section\b.*?</section>)\s*</p>",
    )
    for _ in range(3):
        previous = cleaned
        for pattern in patterns:
            cleaned = re.sub(pattern, r"\1", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if cleaned == previous:
            break

    cleaned = re.sub(
        r"<p\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"<h[1-6]\b[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</h[1-6]>",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return cleaned


def _normalize_template_source(template: str) -> str:
    raw = (template or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        raw = raw[1:-1].strip()
    if any(token in raw for token in ("&lt;", "&gt;", "&#60;", "&#62;", "&#123;", "&#125;", "&#x7b;", "&#x7d;")):
        for _ in range(3):
            decoded = html_unescape(raw)
            if decoded == raw:
                break
            raw = decoded
    raw = raw.replace("\uFF5B", "{").replace("\uFF5D", "}")
    raw = raw.replace("\u00A0", " ")
    raw = raw.replace("\u200B", "").replace("\u200C", "").replace("\u200D", "")
    return raw


def _dedupe_retained_activities_tables(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    pattern = re.compile(
        r"(<h[1-3][^>]*>\s*Les\s+Activites?\s+retenues\s*</h[1-3]>\s*)"
        r"(<table\b.*?</table>\s*)"
        r"(<table\b.*?</table>)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _replace(match: re.Match[str]) -> str:
        heading = match.group(1)
        first_table = match.group(2)
        second_table = match.group(3)
        first_is_services = bool(
            re.search(r"<th[^>]*>\s*Activite\s*</th>", first_table, flags=re.IGNORECASE)
            and not re.search(r"<th[^>]*>\s*Type\s+activite\s*</th>", first_table, flags=re.IGNORECASE)
        )
        second_is_planning = bool(
            re.search(r"<th[^>]*>\s*Type\s+activite\s*</th>", second_table, flags=re.IGNORECASE)
            and re.search(r"<th[^>]*>\s*Lieu\s*</th>", second_table, flags=re.IGNORECASE)
        )
        if first_is_services and second_is_planning:
            return f"{heading}{second_table}"
        return match.group(0)

    return pattern.sub(_replace, raw)


def _cleanup_legacy_terms_layout(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw
    has_table = "<table" in raw.lower()
    if not has_table:
        return raw
    has_table_headers = "<th" in raw.lower()
    table_count = len(re.findall(r"<table\b", raw, flags=re.IGNORECASE))
    if has_table_headers or table_count != 1:
        return raw

    row_pattern = re.compile(
        r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*</tr>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    rows = row_pattern.findall(raw)
    if len(rows) < 4:
        return raw

    flattened = "".join(f"<p>{cell.strip()}</p>" for cell in rows if cell.strip())
    if not flattened:
        return raw
    return flattened


def _enforce_family_page_break(content: str) -> str:
    marker = "quote-page-break"
    pattern = re.compile(r"(<h[1-3][^>]*>\s*Informations?\s+(de\s+la\s+)?famille\s*</h[1-3]>)", re.IGNORECASE)
    match = pattern.search(content or "")
    if match is None:
        return content
    prefix = (content or "")[max(0, match.start() - 260):match.start()]
    if marker in prefix:
        return content
    return (content or "")[:match.start()] + "<div class='quote-page-break'></div>" + (content or "")[match.start():]


_INLINE_FOOTER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-footer[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)

_INLINE_RUNNING_FOOTER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-running-footer[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)


_INLINE_HEADER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-header[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)

_INLINE_RUNNING_HEADER_RE = re.compile(
    r"<table[^>]*class=['\"][^'\"]*quote-running-header[^'\"]*['\"][^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)


_INLINE_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", flags=re.IGNORECASE | re.DOTALL)


def _strip_inline_footers(content: str) -> str:
    without_table = _INLINE_FOOTER_RE.sub("", content or "")
    return _INLINE_RUNNING_FOOTER_RE.sub("", without_table)


def _strip_inline_headers(content: str) -> str:
    without_table = _INLINE_HEADER_RE.sub("", content or "")
    return _INLINE_RUNNING_HEADER_RE.sub("", without_table)


def _strip_overriding_page_styles(content: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        style_body = match.group(1) or ""
        if "@page" in style_body.lower():
            return ""
        return match.group(0)

    return _INLINE_STYLE_RE.sub(_replace, content or "")


def _strip_inline_style_blocks(content: str) -> str:
    return _INLINE_STYLE_RE.sub("", content or "")


def _extract_body_inner_html(content: str) -> str:
    raw = str(content or "")
    matched = re.search(r"<body[^>]*>(.*)</body>", raw, flags=re.IGNORECASE | re.DOTALL)
    if matched is None:
        return raw
    return matched.group(1)


def _normalize_tables_for_pdf(content: str) -> str:
    raw = str(content or "")
    if not raw:
        return raw

    def _normalize_table_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        lowered = tag.lower()
        if (
            "quote-running-header" in lowered
            or "quote-running-footer" in lowered
            or "quote-header" in lowered
            or "quote-footer" in lowered
        ):
            return tag

        updated = tag
        class_match = re.search(r"class\s*=\s*(['\"])(.*?)\1", updated, flags=re.IGNORECASE | re.DOTALL)
        if class_match:
            classes = class_match.group(2)
            if "quote-table" not in classes.split():
                next_classes = f"{classes} quote-table".strip()
                updated = (
                    updated[: class_match.start(2)]
                    + next_classes
                    + updated[class_match.end(2) :]
                )
        else:
            updated = updated[:-1] + " class='quote-table'>"

        if not re.search(r"\bcellpadding\s*=", updated, flags=re.IGNORECASE):
            updated = updated[:-1] + " cellpadding='10'>"
        if not re.search(r"\bcellspacing\s*=", updated, flags=re.IGNORECASE):
            updated = updated[:-1] + " cellspacing='0'>"
        return updated

    def _append_style(existing: str) -> str:
        base = existing.strip()
        if base and not base.endswith(";"):
            base = base + ";"
        extra = (
            "padding:12px 10px 12px 10px;"
            "padding-top:12px;"
            "padding-right:10px;"
            "padding-bottom:12px;"
            "padding-left:10px;"
            "vertical-align:middle;"
        )
        return (base + extra).strip()

    def _normalize_cell_tag(match: re.Match[str]) -> str:
        tag_name = match.group(1)
        attrs = match.group(2) or ""
        updated_attrs = attrs

        style_match = re.search(r"style\s*=\s*(['\"])(.*?)\1", updated_attrs, flags=re.IGNORECASE | re.DOTALL)
        if style_match:
            next_style = _append_style(style_match.group(2))
            updated_attrs = (
                updated_attrs[: style_match.start(2)]
                + next_style
                + updated_attrs[style_match.end(2) :]
            )
        else:
            updated_attrs = f"{updated_attrs} style='{_append_style('')}'"

        if not re.search(r"\bvalign\s*=", updated_attrs, flags=re.IGNORECASE):
            updated_attrs = f"{updated_attrs} valign='middle'"

        return f"<{tag_name}{updated_attrs}>"

    normalized = re.sub(r"<table\b[^>]*>", _normalize_table_tag, raw, flags=re.IGNORECASE)
    normalized = re.sub(r"<(th|td)([^>]*)>", _normalize_cell_tag, normalized, flags=re.IGNORECASE)
    return normalized


def _simplify_rich_text_to_pdf_paragraphs(content: str, *, values: dict[str, str]) -> str:
    normalized = _normalize_template_source(content or "")
    if not normalized:
        return "<p>Aucune condition generale.</p>"
    substituted = _apply_template(normalized, values=values, html_keys=set(), html_output=False)
    raw = str(substituted or "")
    raw = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)<li\b[^>]*>", "• ", raw)
    raw = re.sub(r"(?i)</(p|div|section|h[1-6]|li|tr|table|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)</(td|th)>", "  ", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_unescape(raw)
    raw = raw.replace("\r", "")
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if not lines:
        return "<p>Aucune condition generale.</p>"
    return "".join(f"<p>{escape(line)}</p>" for line in lines)


def _build_quote_pdf_blocks_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> str:
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    terms_html = _simplify_rich_text_to_pdf_paragraphs(cgv_content, values=values)

    template = (
        "<section class='quote-block'>"
        "<h1>Dossier d inscription</h1>"
        "<p><strong>Devis :</strong> {quote_number}</p>"
        "<p><strong>Annee scolaire :</strong> {school_year_label}</p>"
        "<p><strong>Validite :</strong> {expires_at}</p>"
        "<p><strong>Eleve :</strong> {child_full_name}</p>"
        "</section>"
        "{page_break_html}"
        "<h2>Informations famille</h2>"
        "<div class='quote-block'>{prospect_identity_block_html}</div>"
        "{page_break_html}"
        "<h2>Les Activites retenues</h2>"
        "{activities_planning_table_html}"
        "<h2>Prestations</h2>"
        "{services_table_html}"
        "<h2>Remises et supplements</h2>"
        "{adjustments_table_html}"
        "<h2>Materiel</h2>"
        "{products_table_html}"
        "<h2>Kits</h2>"
        "{kits_table_html}"
        "{financial_recap_block_html}"
        "{page_break_html}"
        "<h2>Les modalites de paiement</h2>"
        "{payment_method_block_html}"
        "<p>{payment_schedule_summary}</p>"
        "{payment_schedule_table_html}"
        "<h2>Vos options</h2>"
        "{solfege_block_html}"
        "{masterclass_block_html}"
        "{pass_recup_block_html}"
        "{page_break_html}"
        "<h2>Calendrier des cours</h2>"
        "<p><strong>Resume :</strong> {calendar_summary}</p>"
        "{calendar_activity_semesters_html}"
        "{page_break_html}"
        "<h2>Conditions generales</h2>"
        "<div class='quote-block'>"
        "<p><strong>{cgv_version}</strong></p>"
        "{terms_plain_pdf_html}"
        "</div>"
    )
    block_values = dict(values)
    block_values["cgv_version"] = cgv_label or values.get("cgv_version", "-")
    block_values["terms_plain_pdf_html"] = terms_html
    local_html_keys = set(html_keys)
    local_html_keys.add("terms_plain_pdf_html")
    rendered = _apply_template(template, values=block_values, html_keys=local_html_keys, html_output=True)
    rendered = _cleanup_rendered_block_markup(rendered)
    rendered = _normalize_tables_for_pdf(rendered)
    return rendered


def _pdf_shell_html(*, content_html: str, header_html: str, footer_html: str) -> str:
    return (
        "<html><head><meta charset='utf-8'/>"
        "<style>"
        "@page {"
        "  size: a4 portrait;"
        "  margin: 0;"
        "  @frame header_frame { -pdf-frame-content: header_content; left: 36pt; top: 14pt; width: 523pt; height: 44pt; }"
        "  @frame content_frame { left: 36pt; top: 64pt; width: 523pt; height: 700pt; }"
        "  @frame footer_frame { -pdf-frame-content: footer_content; left: 36pt; top: 770pt; width: 523pt; height: 58pt; }"
        "}"
        "body{font-family:Arial,Helvetica,sans-serif;color:#1f1f1f;font-size:11px;line-height:1.42;}"
        "h1,h2,h3{color:#101828;margin:0 0 8px 0;}"
        "p{margin:0 0 7px 0;}"
        ".quote-page-break{page-break-before:always;}"
        ".quote-block{border:1px solid #d4dae3;background:#fbfcfe;padding:10px;margin:0 0 10px 0;page-break-inside:auto;}"
        ".quote-content table,.quote-table{width:100%;border-collapse:collapse;border-spacing:0;table-layout:auto;margin:8px 0 12px 0;font-size:10.9px;}"
        ".quote-content th,.quote-table th{background:#e7edf7 !important;color:#111827 !important;border:1px solid #c2ccda !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;text-align:left !important;font-weight:700 !important;line-height:1.4 !important;vertical-align:middle !important;white-space:normal !important;word-break:break-word !important;overflow-wrap:anywhere !important;height:auto !important;min-height:30px;}"
        ".quote-content td,.quote-table td{border:1px solid #d3dbe7 !important;padding:12px 10px 12px 10px !important;padding-top:12px !important;padding-right:10px !important;padding-bottom:12px !important;padding-left:10px !important;vertical-align:middle !important;color:#111827 !important;line-height:1.45 !important;word-break:break-word !important;white-space:normal !important;overflow-wrap:anywhere !important;height:auto !important;min-height:30px;}"
        ".quote-content td>*{margin-top:0 !important;margin-bottom:0 !important;}"
        ".quote-content thead,thead{display:table-header-group !important;}"
        ".quote-content tfoot,tfoot{display:table-footer-group !important;}"
        ".quote-content tr,tr{page-break-inside:auto !important;break-inside:auto !important;height:auto !important;}"
        ".quote-brand-logo-img{display:inline-block;max-width:120px;max-height:34px;object-fit:contain;}"
        ".quote-running-header{width:100%;border-collapse:collapse;font-size:10px;color:#334155;border-bottom:1px solid #d7dee8;}"
        ".quote-running-header td{vertical-align:middle;padding:0 0 4px 0;}"
        ".quote-running-footer{width:100%;border-collapse:collapse;font-size:9.4px;color:#475467;border-top:1px solid #d7dee8;}"
        ".quote-running-footer td{vertical-align:top;padding-top:5px;line-height:1.35;}"
        "</style>"
        "</head><body>"
        "<div id='header_content'>"
        f"{header_html}"
        "</div>"
        "<div id='footer_content'>"
        f"{footer_html}"
        "</div>"
        "<div class='quote-content'>"
        f"{content_html}"
        "</div>"
        "</body></html>"
    )


def _build_template_values(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> tuple[dict[str, str], set[str], dict[str, Any]]:
    currency = (quote.currency or "EUR").upper()
    services, products, kits, adjustments = _line_groups(lines)
    document_context = build_quote_document_context(db=db, quote=quote, lines=lines, audience=audience)
    display_flags = document_context["display_flags"]
    total_ttc = Decimal(quote.total_ttc or 0).quantize(Decimal("0.01"))
    total_ht_before_from_lines = sum(
        (Decimal(getattr(line, "amount_ht", Decimal("0")) or Decimal("0")) for line in lines),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    vat_amount_before_from_lines = sum(
        (Decimal(getattr(line, "amount_vat", Decimal("0")) or Decimal("0")) for line in lines),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    if total_ht_before_from_lines <= Decimal("0.00"):
        vat_rate = Decimal("0.00")
    else:
        vat_rate = ((vat_amount_before_from_lines / total_ht_before_from_lines) * Decimal("100")).quantize(Decimal("0.01"))

    payment_terms_snapshot = _json_object(quote.payment_terms_snapshot)
    adjustment_data = _json_object(payment_terms_snapshot.get("adjustment"))
    if not adjustment_data:
        adjustment_data = _json_object(_json_object(quote.meta).get("financial_adjustment"))
    adjustment_type = str(adjustment_data.get("type") or "").strip().lower()
    if adjustment_type not in {"credit", "debt"}:
        adjustment_type = "none"
    adjustment_amount = _decimal_from_any(adjustment_data.get("amount_ttc"), Decimal("0")).quantize(Decimal("0.01"))
    if adjustment_amount <= Decimal("0"):
        adjustment_amount = Decimal("0.00")
        adjustment_type = "none"
    adjustment_signed_amount = (
        -adjustment_amount
        if adjustment_type == "credit"
        else adjustment_amount
        if adjustment_type == "debt"
        else Decimal("0.00")
    )
    total_before_adjustment = (total_ttc - adjustment_signed_amount).quantize(Decimal("0.01"))
    total_after_adjustment = total_ttc
    adjustment_effective_date = _birth_date_label(str(adjustment_data.get("effective_date") or ""))
    adjustment_label = str(adjustment_data.get("label") or "").strip()
    adjustment_type_label = (
        "Avoir" if adjustment_type == "credit" else "Dette" if adjustment_type == "debt" else "Aucun"
    )
    adjustment_impact_label = (
        "Deduit du total facture"
        if adjustment_type == "credit"
        else "Ajoute au total facture"
        if adjustment_type == "debt"
        else ""
    )
    adjustment_display_title = adjustment_type_label if adjustment_type != "none" else ""
    adjustment_display_line = (
        f"{adjustment_display_title} : {_money(adjustment_amount, currency)}"
        if adjustment_type != "none"
        else ""
    )
    has_financial_adjustment = adjustment_type in {"credit", "debt"}
    has_credit_adjustment = adjustment_type == "credit"
    has_debt_adjustment = adjustment_type == "debt"

    total_ht_before_adjustment, vat_amount_before_adjustment = _split_ttc_with_rate(total_before_adjustment, vat_rate)
    total_ht_after_adjustment, vat_amount_after_adjustment = _split_ttc_with_rate(total_after_adjustment, vat_rate)

    if adjustment_type == "none":
        financial_adjustment_block_html = ""
        financial_adjustment_section_html = ""
        financial_adjustment_none_html = "<p>Aucun avoir ou dette applique.</p>"
        total_ttc_before_adjustment_html = ""
    else:
        adjustment_parts = [
            f"<p><strong>{escape(adjustment_display_title)}</strong> : {escape(_money(adjustment_amount, currency))}</p>",
            f"<p><strong>Impact:</strong> {escape(adjustment_impact_label)}</p>",
        ]
        if adjustment_effective_date and adjustment_effective_date != "-":
            adjustment_parts.append(f"<p><strong>Date:</strong> {escape(adjustment_effective_date)}</p>")
        normalized_adjustment_label = adjustment_label.strip().lower()
        normalized_type_label = adjustment_type_label.strip().lower()
        if (
            adjustment_label
            and normalized_adjustment_label not in {"avoir", "dette"}
            and normalized_adjustment_label != normalized_type_label
        ):
            adjustment_parts.append(f"<p><strong>Libelle:</strong> {escape(adjustment_label)}</p>")
        financial_adjustment_block_html = "".join(adjustment_parts)
        # Keep this block content-only (no heading) so it can be safely inserted in WYSIWYG flows.
        financial_adjustment_section_html = financial_adjustment_block_html
        financial_adjustment_none_html = ""
        total_ttc_before_adjustment_html = (
            f"<p><strong>Total TTC avant ajustement :</strong> {_decimal_str(total_before_adjustment)} {escape(currency)}</p>"
        )
    if adjustment_type == "none":
        financial_recap_rows: list[tuple[str, str]] = [
            ("Total HT", f"{_decimal_str(total_ht_after_adjustment)} {currency}"),
            (f"TVA ({_decimal_str(vat_rate)} %)", f"{_decimal_str(vat_amount_after_adjustment)} {currency}"),
            ("Total TTC facture", f"{_decimal_str(total_after_adjustment)} {currency}"),
        ]
    else:
        financial_recap_rows = [
            ("Total TTC avant ajustement", f"{_decimal_str(total_before_adjustment)} {currency}"),
            (adjustment_display_title, f"{_decimal_str(adjustment_amount)} {currency}"),
            ("Impact", adjustment_impact_label),
        ]
        if adjustment_effective_date and adjustment_effective_date != "-":
            financial_recap_rows.append(("Date ajustement", adjustment_effective_date))
        financial_recap_rows.extend(
            [
                ("Total HT facture", f"{_decimal_str(total_ht_after_adjustment)} {currency}"),
                (f"TVA facture ({_decimal_str(vat_rate)} %)", f"{_decimal_str(vat_amount_after_adjustment)} {currency}"),
                ("Total TTC facture", f"{_decimal_str(total_after_adjustment)} {currency}"),
            ]
        )

    financial_recap_lines_html = "".join(
        "<p>"
        f"<strong>{escape(label)} :</strong> {escape(value)}"
        "</p>"
        for label, value in financial_recap_rows
    )
    financial_recap_block_html = (
        "<div class='quote-block'>"
        "<h2>Recapitulatif financier</h2>"
        f"{financial_recap_lines_html}"
        "</div>"
    )

    services_table_html = _table_html(
        ["Activite", "Quantite", "Duree", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                f"{int(line.duration_minutes)} min" if line.duration_minutes else "-",
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in services
        ],
        empty_label="Aucune activite.",
    )
    products_table_html = _table_html(
        ["Materiel", "Quantite", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in products
        ],
        empty_label="Aucun materiel.",
    )
    kits_table_html = _table_html(
        ["Kit", "Quantite", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in kits
        ],
        empty_label="Aucun kit.",
    )
    adjustments_table_html = _table_html(
        ["Type", "Intitule", "Quantite", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                "Remise"
                if (line.line_type or "").strip().lower() == "discount"
                else "Supplement"
                if (line.line_type or "").strip().lower() == "surcharge"
                else (
                    "Remise"
                    if (line.master_item_type or "").strip().lower() == "discount_rule"
                    else "Supplement"
                ),
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in adjustments
        ],
        empty_label="Aucune remise ni supplement.",
    )
    lines_table_html = _table_html(
        ["Categorie", "Intitule", "Quantite", "TVA", "PU TTC", "Montant TTC"],
        [
            [
                "Remise"
                if (line.line_type or "").strip().lower() == "discount"
                else "Supplement"
                if (line.line_type or "").strip().lower() == "surcharge"
                else ("Service" if (line.line_category or "").lower() == "service" else ("Kit" if line.kit_id else "Materiel")),
                line.title or "-",
                _decimal_str(Decimal(line.quantity or 0)),
                f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
                _money(Decimal(line.unit_price_ttc or 0), currency),
                _money(Decimal(line.amount_ttc or 0), currency),
            ]
            for line in lines
        ],
        empty_label="Aucune ligne.",
    )

    schedule = document_context["schedule"]
    payment_schedule_rows = [
        [
            str(item.get("label") or "-"),
            f"{item.get('amount_ttc', '-')}" + (f" {item.get('currency')}" if item.get("currency") else ""),
            _schedule_due_label(item),
            str(item.get("payment_method") or "-"),
        ]
        for item in schedule
    ]
    payment_schedule_table_html = _table_html(
        ["Echeance", "Montant", "Quand", "Type"],
        payment_schedule_rows,
        empty_label="Aucun echeancier.",
    )
    if not display_flags["showPaymentScheduleDetailed"]:
        compact_notice = str(document_context["payment_schedule_compact_notice"] or "").strip()
        if schedule and len(schedule) <= 1:
            payment_schedule_table_html = ""
        elif compact_notice:
            payment_schedule_table_html = f"<p>{escape(compact_notice)}</p>"
        elif not schedule:
            payment_schedule_table_html = "<p>Aucun échéancier.</p>"
        else:
            payment_schedule_table_html = ""

    sessions = [item for item in _json_list(_json_object(quote.calendar_snapshot).get("sessions")) if isinstance(item, dict)]
    planning_blocks_table_html = _planning_blocks_table_html(_json_object(quote.calendar_snapshot))
    calendar_sessions_table_html = _table_html(
        ["Date", "Debut", "Fin", "Duree", "Modalite"],
        [
            [
                str(item.get("date") or "-"),
                str(item.get("start_time") or item.get("start_at") or "-"),
                str(item.get("end_time") or item.get("end_at") or "-"),
                f"{item.get('duration_minutes')} min" if item.get("duration_minutes") is not None else "-",
                str(item.get("modality") or "-"),
            ]
            for item in sessions
        ],
        empty_label="Aucun cours planifie.",
    )
    calendar_table_html, calendar_activities_count = _calendar_visual_summary(sessions)
    calendar_summary = (
        f"{len(sessions)} seances planifiees sur {calendar_activities_count} activites"
        if sessions
        else "Aucune seance planifiee"
    )
    if schedule:
        due_labels = ", ".join(_schedule_due_label(item) for item in schedule)
        unit_label = "échéance" if len(schedule) == 1 else "échéances"
        payment_schedule_summary = f"{len(schedule)} {unit_label} : {due_labels}"
    else:
        payment_schedule_summary = "Paiement non planifie"

    cgv_label, _ = _load_terms_template_content(db=db, quote=quote)
    prospect_data = document_context["prospect_data"]
    client_data = document_context["client_data"]
    recipient_name = (
        prospect_data.get("parent_full_name")
        or prospect_data.get("adult_full_name")
        or client_data.get("client_full_name")
        or "-"
    )
    recipient_email = (
        prospect_data.get("parent_email")
        or prospect_data.get("adult_email")
        or client_data.get("client_email")
        or "-"
    )
    payment_method_label = str(document_context["payment_method_label"] or "Paiement non precise")
    solfege_slot = _json_object(document_context.get("solfege_selected_slot"))
    solfege_slot_label = str(solfege_slot.get("label") or "").strip()
    if not solfege_slot_label and solfege_slot:
        day = str(solfege_slot.get("weekday_label") or solfege_slot.get("weekday") or "").strip()
        start = str(solfege_slot.get("start_time") or "--:--").strip()
        end = str(solfege_slot.get("end_time") or "--:--").strip()
        solfege_slot_label = f"{day} {start}-{end}".strip()
    solfege_duration = document_context.get("solfege_duration_minutes")
    solfege_duration_label = f" ({solfege_duration} min)" if solfege_duration else ""
    solfege_slot_suffix = f" · {solfege_slot_label}" if solfege_slot_label else ""
    solfege_full = (
        f"Solfege souscrit - Niveau {document_context.get('solfege_level') or '-'}"
        f"{solfege_duration_label}"
        f"{solfege_slot_suffix}"
    )
    masterclass_blocks = _json_list(document_context.get("masterclass_blocks"))
    masterclass_full = "Masterclass du samedi souscrite."
    if masterclass_blocks:
        labels: list[str] = []
        for block in masterclass_blocks[:3]:
            if not isinstance(block, dict):
                continue
            session = str(block.get("session") or "").strip()
            location = str(block.get("location_label") or "").strip()
            label = " · ".join(part for part in (session, location) if part)
            if label:
                labels.append(label)
        if labels:
            masterclass_full = f"Masterclass du samedi souscrite - {'; '.join(labels)}"

    def _identity_row_cells(label: str, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized or normalized == "-":
            return ""
        return (
            "<tr>"
            f"<td>{escape(label)}</td>"
            f"<td>{escape(normalized)}</td>"
            "</tr>"
        )

    def _identity_card(title: str, rows: list[str], empty_label: str) -> str:
        body = "".join(row for row in rows if row)
        if not body:
            body = (
                "<tr>"
                f"<td>{escape(empty_label)}</td>"
                "<td>-</td>"
                "</tr>"
            )
        return (
            "<section class='quote-identity-card'>"
            f"<h3>{escape(title)}</h3>"
            "<table class='quote-identity-meta' cellspacing='0' cellpadding='0'>"
            f"{body}"
            "</table>"
            "</section>"
        )

    adult_email_value = prospect_data.get("adult_email") or recipient_email
    adult_phone_value = str(prospect_data.get("adult_phone") or client_data.get("client_phone") or "").strip()
    adult_address_value = str(prospect_data.get("adult_address") or client_data.get("client_address") or "").strip()

    child_birth_date_value = _birth_date_label(str(prospect_data.get("child_birth_date") or ""))
    parent_email_value = prospect_data.get("parent_email") or recipient_email
    parent_phone_value = str(prospect_data.get("parent_phone") or "").strip()
    parent_address_value = str(prospect_data.get("parent_address") or "").strip()
    responsible_name_value = str(
        prospect_data.get("parent_full_name")
        or prospect_data.get("adult_full_name")
        or recipient_name
        or "-"
    ).strip()
    responsible_email_value = str(parent_email_value or adult_email_value or "").strip()
    responsible_phone_value = str(parent_phone_value or adult_phone_value or "").strip()
    responsible_address_value = str(parent_address_value or adult_address_value or "").strip()

    child_identity_card_html = _identity_card(
        "Informations de l eleve",
        [
            _identity_row_cells("Eleve", str(prospect_data.get("child_full_name") or "-")),
            _identity_row_cells("Date de naissance", child_birth_date_value),
        ],
        "Eleve",
    )
    responsible_identity_card_html = _identity_card(
        "Informations de l adulte responsable",
        [
            _identity_row_cells("Adulte responsable", responsible_name_value),
            _identity_row_cells("Email", responsible_email_value),
            _identity_row_cells("Telephone", responsible_phone_value),
            _identity_row_cells("Adresse", responsible_address_value),
        ],
        "Adulte responsable",
    )
    adult_identity_card_html = _identity_card(
        "Informations de l adulte responsable",
        [
            _identity_row_cells("Adulte responsable", str(prospect_data.get("adult_full_name") or recipient_name or "-")),
            _identity_row_cells("Email", str(adult_email_value or "")),
            _identity_row_cells("Telephone", adult_phone_value),
            _identity_row_cells("Adresse", adult_address_value),
        ],
        "Adulte responsable",
    )
    prospect_identity_block_html = (
        "<div class='quote-identity-grid'>"
        + (child_identity_card_html + responsible_identity_card_html if display_flags["showChildBlock"] else adult_identity_card_html)
        + "</div>"
    )
    solfege_block_html = (
        f"<p>{escape(solfege_full)}</p>"
        if display_flags["showSolfegeSection"]
        else "<p>Solfege non souscrit. Aucun cours de solfege n est inclus dans cette formule.</p>"
    )
    masterclass_block_html = (
        f"<p>{escape(masterclass_full)}</p>"
        if display_flags["showMasterclassSection"]
        else "<p>Masterclass du samedi : non souscrite.</p>"
    )
    pass_recup_block_html = (
        "<p>Option Pass Recup souscrite. Les regles d usage sont appliquees selon la formule.</p>"
        if display_flags["showPassRecupSection"]
        else "<p>Option Pass Recup : non souscrite. Aucun rattrapage de cours n est inclus dans cette formule.</p>"
    )
    payment_instruction = str(document_context.get("payment_instruction") or "").strip()
    payment_method_block_html = f"<p><strong>Mode de paiement :</strong> {escape(payment_method_label)}</p>"
    if payment_instruction:
        payment_method_block_html = (
            f"{payment_method_block_html}<p><strong>Consignes :</strong> {escape(payment_instruction)}</p>"
        )

    brand_logo_html = _brand_logo_html(db=db, variant="header")
    cover_logo_html = _brand_logo_html(db=db, variant="cover")
    header_standard_html = (
        "<table class='quote-running-header' width='100%' cellspacing='0' cellpadding='0'>"
        "<tr>"
        "<td width='68%' align='left' valign='middle'>"
        "<span style='font-size:11px;font-weight:700;color:#111827;'>PIANO ACADEMIE</span>"
        "</td>"
        "<td width='32%' align='right' valign='middle' style='font-size:10px;color:#334155;'>"
        f"<strong>Devis {escape(quote.quote_number or '-')}</strong>"
        "</td>"
        "</tr>"
        "</table>"
    )
    cover_page_standard_html = (
        "<section class='quote-cover'>"
        f"{cover_logo_html}"
        "<h1 class='quote-cover-title'>Dossier d inscription</h1>"
        f"<p class='quote-cover-subtitle'>Annee scolaire {escape(quote.school_year_label or '-')}</p>"
        f"<p class='quote-cover-name'>{escape(prospect_data.get('child_full_name') or recipient_name)}</p>"
        "<div class='quote-cover-meta'>"
        f"<p>Type de prospect: {escape(str(prospect_data.get('prospect_type_label') or '-'))}</p>"
        f"<p>Document genere le {escape(_datetime_label(_utcnow()))}</p>"
        f"<p>Valable jusqu au {escape(_date_label(quote.expires_at))}</p>"
        "</div>"
        "</section>"
        "<div class='quote-page-break'></div>"
    )

    values: dict[str, str] = {
        "quote_number": quote.quote_number or "-",
        "recipient_name": recipient_name,
        "recipient_email": recipient_email,
        "total_ttc": _decimal_str(total_ttc),
        "total_ttc_before_adjustment": _decimal_str(total_before_adjustment),
        "total_ttc_after_adjustment": _decimal_str(total_after_adjustment),
        "total_ht": _decimal_str(total_ht_after_adjustment),
        "total_ht_before_adjustment": _decimal_str(total_ht_before_adjustment),
        "total_ht_after_adjustment": _decimal_str(total_ht_after_adjustment),
        "vat_rate": _decimal_str(vat_rate),
        "vat_amount": _decimal_str(vat_amount_after_adjustment),
        "vat_amount_before_adjustment": _decimal_str(vat_amount_before_adjustment),
        "vat_amount_after_adjustment": _decimal_str(vat_amount_after_adjustment),
        "currency": currency,
        "expires_at": _date_label(quote.expires_at),
        "sent_at": _datetime_label(quote.sent_at),
        "generated_at": _datetime_label(_utcnow()),
        "school_year_label": (quote.school_year_label or "-"),
        "calendar_summary": calendar_summary,
        "payment_schedule_summary": payment_schedule_summary,
        "financial_adjustment_type": adjustment_type,
        "financial_adjustment_type_label": adjustment_type_label,
        "financial_adjustment_amount_ttc": _decimal_str(adjustment_amount),
        "financial_adjustment_signed_amount_ttc": _decimal_str(adjustment_signed_amount),
        "financial_adjustment_effective_date": adjustment_effective_date,
        "financial_adjustment_label": adjustment_label,
        "financial_adjustment_display_title": adjustment_display_title if has_financial_adjustment else "",
        "financial_adjustment_display_line": adjustment_display_line,
        "financial_adjustment_impact_label": adjustment_impact_label,
        "has_financial_adjustment": "true" if has_financial_adjustment else "false",
        "has_credit_adjustment": "true" if has_credit_adjustment else "false",
        "has_debt_adjustment": "true" if has_debt_adjustment else "false",
        "financial_adjustment_block_html": financial_adjustment_block_html,
        "financial_adjustment_section_html": financial_adjustment_section_html,
        "financial_adjustment_none_html": financial_adjustment_none_html,
        "financial_recap_block_html": financial_recap_block_html,
        "total_ttc_before_adjustment_html": total_ttc_before_adjustment_html,
        "total_before_adjustment": _decimal_str(total_before_adjustment),
        "total_after_adjustment": _decimal_str(total_after_adjustment),
        "payment_method_label": payment_method_label,
        "payment_instruction": payment_instruction,
        "payment_schedule_compact_notice": document_context["payment_schedule_compact_notice"] or "",
        "document_style_html": _document_style_html(),
        "brand_logo_html": brand_logo_html,
        "header_standard_html": header_standard_html,
        "cover_page_standard_html": cover_page_standard_html,
        "page_break_html": "<div class='quote-page-break'></div>",
        "footer_standard_html": (
            "<table class='quote-running-footer' width='100%' cellspacing='0' cellpadding='0'>"
            "<tr>"
            "<td width='33%' align='left' valign='top'>"
            "Piano Academie<br/>"
            "1 rue de Richelieu<br/>"
            "75001 Paris"
            "</td>"
            "<td width='34%' align='center' valign='top'>"
            "SIRET 82805141700032<br/>"
            "FR 74828051417"
            "</td>"
            f"<td width='33%' align='right' valign='top'>{escape(quote.quote_number or '-')}</td>"
            "</tr>"
            "</table>"
        ),
        "cgv_version": cgv_label or "-",
        "services_count": str(len(services)),
        "products_count": str(len(products)),
        "kits_count": str(len(kits)),
        "adjustments_count": str(len(adjustments)),
        "lines_count": str(len(lines)),
        "prospect_identity_block_html": prospect_identity_block_html,
        "solfege_block_html": solfege_block_html,
        "masterclass_block_html": masterclass_block_html,
        "pass_recup_block_html": pass_recup_block_html,
        "payment_method_block_html": payment_method_block_html,
        "services_table_html": services_table_html,
        "activities_planning_table_html": planning_blocks_table_html,
        "products_table_html": products_table_html,
        "kits_table_html": kits_table_html,
        "adjustments_table_html": adjustments_table_html,
        "lines_table_html": lines_table_html,
        "payment_schedule_table_html": payment_schedule_table_html,
        "calendar_table_html": calendar_table_html,
        "calendar_activity_semesters_html": calendar_table_html,
        "calendar_sessions_table_html": calendar_sessions_table_html,
        "show_adult_block": "true" if display_flags["showAdultBlock"] else "false",
        "show_child_block": "true" if display_flags["showChildBlock"] else "false",
        "show_solfege_section": "true" if display_flags["showSolfegeSection"] else "false",
        "show_masterclass_section": "true" if display_flags["showMasterclassSection"] else "false",
        "show_pass_recup_section": "true" if display_flags["showPassRecupSection"] else "false",
        "show_payment_schedule_detailed": "true" if display_flags["showPaymentScheduleDetailed"] else "false",
    }
    values.update(prospect_data)
    values.update(client_data)

    html_keys = {
        "prospect_identity_block_html",
        "solfege_block_html",
        "masterclass_block_html",
        "pass_recup_block_html",
        "payment_method_block_html",
        "financial_adjustment_block_html",
        "financial_adjustment_section_html",
        "financial_adjustment_none_html",
        "financial_recap_block_html",
        "total_ttc_before_adjustment_html",
        "services_table_html",
        "activities_planning_table_html",
        "products_table_html",
        "kits_table_html",
        "adjustments_table_html",
        "lines_table_html",
        "payment_schedule_table_html",
        "calendar_table_html",
        "calendar_activity_semesters_html",
        "calendar_sessions_table_html",
        "document_style_html",
        "brand_logo_html",
        "header_standard_html",
        "cover_page_standard_html",
        "page_break_html",
        "footer_standard_html",
    }
    return values, html_keys, document_context


def _default_quote_body_template() -> str:
    return (
        "{document_style_html}"
        "{cover_page_standard_html}"
        "{header_standard_html}"
        "<h1>Devis {quote_number}</h1>"
        "<p><strong>Destinataire:</strong> {recipient_name} ({recipient_email})</p>"
        "<p><strong>Annee scolaire:</strong> {school_year_label}</p>"
        "<p><strong>Expiration:</strong> {expires_at}</p>"
        "{page_break_html}"
        "<h2>Informations famille</h2>"
        "<div class='quote-block'>"
        "{prospect_identity_block_html}"
        "</div>"
        "<h2>Activites</h2>{services_table_html}"
        "<h3>Planning detaille des activites</h3>{activities_planning_table_html}"
        "<h2>Materiel</h2>{products_table_html}"
        "<h2>Kits</h2>{kits_table_html}"
        "<h2>Remises et supplements</h2>{adjustments_table_html}"
        "{payment_method_block_html}"
        "<h2>Echeancier de paiement</h2>{payment_schedule_table_html}"
        "{financial_adjustment_section_html}"
        "{solfege_block_html}"
        "{masterclass_block_html}"
        "{pass_recup_block_html}"
        "<h2>Calendrier des cours</h2>{calendar_table_html}"
        "{financial_recap_block_html}"
        "{footer_standard_html}"
    )


def _render_quote_body_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    _, body_template = _load_quote_template_snapshot(db=db, quote=quote)
    template = _normalize_template_source(body_template or _default_quote_body_template())
    if "{financial_recap_block_html}" not in template:
        legacy_financial_tokens = (
            "{total_ttc_before_adjustment_html}",
            "{total_ht_before_adjustment}",
            "{vat_amount_before_adjustment}",
            "{total_ht_after_adjustment}",
            "{vat_amount_after_adjustment}",
            "{total_ttc_after_adjustment}",
            "{total_ht}",
            "{vat_amount}",
            "{total_after_adjustment}",
            "{total_ttc}",
        )
        if any(token in template for token in legacy_financial_tokens):
            template = re.sub(
                r"<p[^>]*>\s*<strong>\s*"
                r"(?:Total(?:\s+TTC(?:\s+avant\s+ajustement|\s+facture)?|\s+HT(?:\s+avant\s+ajustement)?|"
                r"\s+avant\s+ajustement)|TVA(?:\s*\([^)]+\))?(?:\s+avant\s+ajustement|\s+facture)?)"
                r"\s*:?\s*</strong>.*?</p>",
                "",
                template,
                flags=re.IGNORECASE | re.DOTALL,
            )
            template += "{financial_recap_block_html}"
    template = _normalize_block_placeholder_wrappers(
        template,
        keys={
            "document_style_html",
            "brand_logo_html",
            "header_standard_html",
            "cover_page_standard_html",
            "page_break_html",
            "footer_standard_html",
            "prospect_identity_block_html",
            "solfege_block_html",
            "masterclass_block_html",
            "pass_recup_block_html",
            "payment_method_block_html",
            "services_table_html",
            "activities_planning_table_html",
            "products_table_html",
            "kits_table_html",
            "adjustments_table_html",
            "lines_table_html",
            "payment_schedule_table_html",
            "calendar_table_html",
            "calendar_activity_semesters_html",
            "calendar_sessions_table_html",
            "financial_adjustment_block_html",
            "financial_adjustment_section_html",
            "financial_adjustment_none_html",
            "financial_recap_block_html",
        },
    )
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    rendered = _apply_template(template, values=values, html_keys=html_keys, html_output=True)
    rendered = _cleanup_rendered_block_markup(rendered)
    rendered = _dedupe_retained_activities_tables(rendered)
    if "{activities_planning_table_html}" not in template.lower():
        rendered += (
            "<h3>Planning detaille des activites</h3>"
            + values.get("activities_planning_table_html", "<p>Aucun bloc planning.</p>")
        )
    rendered = _enforce_family_page_break(rendered)
    return _as_html_fragment(rendered)


def _render_quote_terms_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    values, html_keys, _ = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    normalized_terms = _normalize_template_source(cgv_content)
    normalized_terms = _normalize_block_placeholder_wrappers(
        normalized_terms,
        keys={
            "document_style_html",
            "brand_logo_html",
            "header_standard_html",
            "cover_page_standard_html",
            "page_break_html",
            "footer_standard_html",
            "prospect_identity_block_html",
            "payment_method_block_html",
            "payment_schedule_table_html",
            "calendar_table_html",
            "calendar_activity_semesters_html",
            "financial_recap_block_html",
        },
    )
    rendered_terms = _apply_template(normalized_terms, values=values, html_keys=html_keys, html_output=True)
    rendered_terms = _cleanup_rendered_block_markup(rendered_terms)
    rendered_terms = _normalize_template_source(rendered_terms)
    rendered_terms = _cleanup_legacy_terms_layout(rendered_terms)
    header_html = values.get("header_standard_html", "")
    footer_html = values.get("footer_standard_html", "")
    return (
        "<section>"
        f"{header_html}"
        "<h2 class='quote-terms-title'>Conditions generales</h2>"
        "<div class='quote-block'>"
        f"<p><strong>{escape(cgv_label or 'Version non precisee')}</strong></p>"
        f"{_as_html_fragment(rendered_terms or 'Aucune CGV snapshottee.')}"
        "</div>"
        f"{footer_html}"
        "</section>"
    )


def render_quote_combined_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    body_html = _render_quote_body_html(db=db, quote=quote, lines=lines, audience=audience)
    terms_html = _render_quote_terms_html(db=db, quote=quote, lines=lines, audience=audience)
    base_css = _document_style_html()
    return (
        "<html><head><meta charset='utf-8'/>"
        f"{base_css}"
        "</head><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"{base_css}"
        f"<section>{body_html}</section>"
        "<div class='quote-page-break'></div>"
        f"{terms_html}"
        "</body></html>"
    )


def render_quote_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> str:
    return render_quote_combined_html(db=db, quote=quote, lines=lines, audience=audience)


def render_quote_parts_html(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> tuple[str, str, str]:
    body_html = _render_quote_body_html(db=db, quote=quote, lines=lines, audience=audience)
    terms_html = _render_quote_terms_html(db=db, quote=quote, lines=lines, audience=audience)
    base_css = _document_style_html()
    combined_html = (
        "<html><head><meta charset='utf-8'/>"
        f"{base_css}"
        "</head><body style='font-family:Arial,sans-serif;color:#1a1a1a;'>"
        f"{base_css}"
        f"<section>{body_html}</section>"
        "<div class='quote-page-break'></div>"
        f"{terms_html}"
        "</body></html>"
    )
    return body_html, terms_html, combined_html


def render_quote_document_bundle(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> dict[str, Any]:
    values, _, context = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    body_html, terms_html, combined_html = render_quote_parts_html(db=db, quote=quote, lines=lines, audience=audience)
    return {
        "audience": audience,
        "quote_id": str(quote.id),
        "quote_number": quote.quote_number,
        "body_html": body_html,
        "terms_html": terms_html,
        "combined_html": combined_html,
        "display_flags": context.get("display_flags", {}),
        "visible_blocks": context.get("visible_blocks", []),
        "hidden_blocks": context.get("hidden_blocks", []),
        "payment_method_label": values.get("payment_method_label", ""),
        "payment_schedule_compact_notice": values.get("payment_schedule_compact_notice", ""),
    }


def render_quote_pdf(
    *,
    db: Session | None = None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str = DEFAULT_AUDIENCE,
) -> bytes:
    # Robust path: render from stable business blocks (no fragile HTML frame layout).
    return _render_quote_pdf_blocks(db=db, quote=quote, lines=lines, audience=audience)


def _safe_logo_reader(data_url: str) -> ImageReader | None:
    raw = str(data_url or "").strip()
    if not raw.startswith("data:image/") or "," not in raw:
        return None
    payload = raw.split(",", 1)[1]
    try:
        content = base64.b64decode(payload, validate=False)
    except Exception:
        return None
    try:
        return ImageReader(io.BytesIO(content))
    except Exception:
        return None


def _quote_pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=8,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475467"),
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=2,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=4,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#111827"),
            spaceBefore=2,
            spaceAfter=5,
        ),
        "text": ParagraphStyle(
            "text",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=5,
        ),
        "text_center": ParagraphStyle(
            "text_center",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=5,
        ),
        "small_muted": ParagraphStyle(
            "small_muted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#667085"),
            spaceAfter=4,
        ),
    }


def _table_for_pdf(headers: list[str], rows: list[list[str]], *, width: float) -> Table:
    data = [headers] + (rows if rows else [["-", "-", "-", "-", "-", "-"][: len(headers)]])
    col_count = len(headers) if headers else 1
    col_width = width / col_count
    table = Table(data, colWidths=[col_width] * col_count, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EDF7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10.5),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.9, colors.HexColor("#c4cfde")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 10.5),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#111827")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _terms_lines_for_pdf(content: str, *, values: dict[str, str]) -> list[str]:
    normalized = _normalize_template_source(content or "")
    if not normalized:
        return ["Aucune condition generale."]
    substituted = _apply_template(normalized, values=values, html_keys=set(), html_output=False)
    raw = str(substituted or "")
    raw = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)<li\b[^>]*>", "• ", raw)
    raw = re.sub(r"(?i)</(p|div|section|h[1-6]|li|tr|table|ul|ol)>", "\n", raw)
    raw = re.sub(r"(?i)</(td|th)>", "  ", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_unescape(raw)
    raw = raw.replace("\r", "")
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    return lines or ["Aucune condition generale."]


def _draw_quote_pdf_header_footer(
    canvas_obj: Any,
    doc: SimpleDocTemplate,
    *,
    quote_number: str,
    logo_reader: ImageReader | None,
) -> None:
    canvas_obj.saveState()
    page_width, page_height = A4
    left_x = doc.leftMargin
    right_x = page_width - doc.rightMargin

    header_top = page_height - 13 * mm
    if logo_reader is not None:
        try:
            canvas_obj.drawImage(
                logo_reader,
                left_x,
                header_top - 12 * mm,
                width=28 * mm,
                height=10 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            logo_reader = None

    canvas_obj.setFont("Helvetica-Bold", 11)
    canvas_obj.setFillColor(colors.HexColor("#0f172a"))
    if logo_reader is None:
        canvas_obj.drawString(left_x, header_top - 6 * mm, "PIANO ACADEMIE")
    canvas_obj.drawRightString(right_x, header_top - 6 * mm, f"Devis {quote_number or '-'}")
    canvas_obj.setStrokeColor(colors.HexColor("#cfd8e6"))
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(left_x, page_height - 24 * mm, right_x, page_height - 24 * mm)

    footer_y = 15 * mm
    canvas_obj.setStrokeColor(colors.HexColor("#cfd8e6"))
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(left_x, footer_y + 11 * mm, right_x, footer_y + 11 * mm)
    canvas_obj.setFont("Helvetica", 9.5)
    canvas_obj.setFillColor(colors.HexColor("#334155"))
    canvas_obj.drawString(left_x, footer_y + 6 * mm, "Piano Academie")
    canvas_obj.drawString(left_x, footer_y + 2 * mm, "1 rue de Richelieu")
    canvas_obj.drawString(left_x, footer_y - 2 * mm, "75001 Paris")
    canvas_obj.drawCentredString((left_x + right_x) / 2, footer_y + 6 * mm, "SIRET 82805141700032")
    canvas_obj.drawCentredString((left_x + right_x) / 2, footer_y + 2 * mm, "FR 74828051417")
    canvas_obj.drawRightString(right_x, footer_y + 6 * mm, quote_number or "-")
    canvas_obj.restoreState()


def _render_quote_pdf_blocks(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    audience: str,
) -> bytes:
    values, _, context = _build_template_values(db=db, quote=quote, lines=lines, audience=audience)
    prospect_data = context.get("prospect_data", {})
    calendar_snapshot = _json_object(quote.calendar_snapshot)
    sessions = [item for item in _json_list(calendar_snapshot.get("sessions")) if isinstance(item, dict)]
    planning_blocks = [item for item in _json_list(calendar_snapshot.get("blocks")) if isinstance(item, dict)]
    services, products, kits, adjustments = _line_groups(lines)
    cgv_label, cgv_content = _load_terms_template_content(db=db, quote=quote)
    terms_lines = _terms_lines_for_pdf(cgv_content, values=values)
    schedule = [item for item in _json_list(context.get("schedule")) if isinstance(item, dict)]
    styles = _quote_pdf_styles()
    logo_reader = _safe_logo_reader(_account_logo_data_url(db=db))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=30 * mm,
        bottomMargin=24 * mm,
        title=f"Devis {quote.quote_number or '-'}",
        author="Piano Academie",
    )
    content_width = A4[0] - doc.leftMargin - doc.rightMargin
    story: list[Any] = []

    story.append(Spacer(1, 18 * mm))
    story.append(Paragraph("Dossier d inscription", styles["cover_title"]))
    story.append(Paragraph(f"Devis : {escape(values.get('quote_number', '-'))}", styles["cover_subtitle"]))
    story.append(Paragraph(f"Annee scolaire : {escape(values.get('school_year_label', '-'))}", styles["cover_subtitle"]))
    story.append(Paragraph(f"Validite : {escape(values.get('expires_at', '-'))}", styles["cover_subtitle"]))
    story.append(
        Paragraph(
            f"Eleve : {escape(prospect_data.get('child_full_name') or values.get('recipient_name', '-'))}",
            styles["cover_subtitle"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("Informations famille", styles["h1"]))
    identity_rows: list[list[str]] = []
    if str(prospect_data.get("prospect_type") or "").lower() == "child":
        identity_rows.extend(
            [
                ["Eleve", str(prospect_data.get("child_full_name") or "-")],
                ["Date de naissance", _birth_date_label(str(prospect_data.get("child_birth_date") or ""))],
                ["Adulte responsable", str(prospect_data.get("parent_full_name") or "-")],
                ["Email adulte responsable", str(prospect_data.get("parent_email") or values.get("recipient_email") or "-")],
                ["Telephone adulte responsable", str(prospect_data.get("parent_phone") or "-")],
                ["Adresse adulte responsable", str(prospect_data.get("parent_address") or "-")],
            ]
        )
    else:
        identity_rows.extend(
            [
                ["Adulte responsable", str(prospect_data.get("adult_full_name") or values.get("recipient_name") or "-")],
                ["Email", str(prospect_data.get("adult_email") or values.get("recipient_email") or "-")],
                ["Telephone", str(prospect_data.get("adult_phone") or "-")],
                ["Adresse", str(prospect_data.get("adult_address") or "-")],
            ]
        )
    story.append(_table_for_pdf(["Champ", "Valeur"], identity_rows, width=content_width))
    story.append(Spacer(1, 5))
    story.append(Paragraph(f"Email contact : {escape(values.get('recipient_email', '-'))}", styles["text"]))
    story.append(PageBreak())

    story.append(Paragraph("Les Activites retenues", styles["h1"]))
    planning_rows: list[list[str]] = []
    for block in planning_blocks:
        activity_type = _modality_label(block.get("modality"))
        activity = str(block.get("activity_label") or "-")
        location = str(block.get("location_label") or "-")
        day = str(block.get("weekday_label") or _weekday_label(block.get("weekday")) or "-")
        start = str(block.get("start_time") or "").strip()
        end = str(block.get("end_time") or "").strip()
        time_range = f"{start} - {end}" if start and end else "-"
        duration = _duration_label(
            start_time=block.get("start_time"),
            end_time=block.get("end_time"),
            fallback_minutes=block.get("duration_minutes"),
        )
        planning_rows.append([activity_type, activity, location, day, time_range, duration])
    story.append(_table_for_pdf(["Type activite", "Activite", "Lieu", "Jour", "Horaire", "Duree"], planning_rows, width=content_width))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Prestations", styles["h2"]))
    service_rows = [
        [
            line.title or "-",
            _decimal_str(Decimal(line.quantity or 0)),
            f"{int(line.duration_minutes)} min" if line.duration_minutes else "-",
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in services
    ]
    story.append(_table_for_pdf(["Activite", "Quantite", "Duree", "TVA", "PU TTC", "Montant TTC"], service_rows, width=content_width))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Remises et supplements", styles["h2"]))
    adjustment_rows = [
        [
            "Remise"
            if (line.line_type or "").strip().lower() == "discount"
            else "Supplement"
            if (line.line_type or "").strip().lower() == "surcharge"
            else (
                "Remise"
                if (line.master_item_type or "").strip().lower() == "discount_rule"
                else "Supplement"
            ),
            line.title or "-",
            _decimal_str(Decimal(line.quantity or 0)),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in adjustments
    ]
    story.append(_table_for_pdf(["Type", "Intitule", "Quantite", "TVA", "PU TTC", "Montant TTC"], adjustment_rows, width=content_width))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Materiel", styles["h2"]))
    product_rows = [
        [
            line.title or "-",
            _decimal_str(Decimal(line.quantity or 0)),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in products
    ]
    story.append(_table_for_pdf(["Materiel", "Quantite", "TVA", "PU TTC", "Montant TTC"], product_rows, width=content_width))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Kits", styles["h2"]))
    kit_rows = [
        [
            line.title or "-",
            _decimal_str(Decimal(line.quantity or 0)),
            f"{_decimal_str(Decimal(getattr(line, 'vat_rate', 0) or 0))} %",
            _money(Decimal(line.unit_price_ttc or 0), values.get("currency", "EUR")),
            _money(Decimal(line.amount_ttc or 0), values.get("currency", "EUR")),
        ]
        for line in kits
    ]
    story.append(_table_for_pdf(["Kit", "Quantite", "TVA", "PU TTC", "Montant TTC"], kit_rows, width=content_width))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Recapitulatif financier", styles["h2"]))
    financial_rows: list[list[str]] = []
    if values.get("has_financial_adjustment") == "true":
        financial_rows.append(["Total TTC avant ajustement", f"{values.get('total_ttc_before_adjustment', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append([values.get("financial_adjustment_type_label", "Ajustement"), f"{values.get('financial_adjustment_amount_ttc', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append(["Impact", values.get("financial_adjustment_impact_label", "-")])
        effective_date = values.get("financial_adjustment_effective_date", "")
        if effective_date and effective_date != "-":
            financial_rows.append(["Date ajustement", effective_date])
        financial_rows.append(["Total HT facture", f"{values.get('total_ht_after_adjustment', values.get('total_ht', '0,00'))} {values.get('currency', 'EUR')}"])
        financial_rows.append([f"TVA facture ({values.get('vat_rate', '0,00')} %)", f"{values.get('vat_amount_after_adjustment', values.get('vat_amount', '0,00'))} {values.get('currency', 'EUR')}"])
        financial_rows.append(["Total TTC facture", f"{values.get('total_ttc_after_adjustment', values.get('total_ttc', '0,00'))} {values.get('currency', 'EUR')}"])
    else:
        financial_rows.append(["Total HT", f"{values.get('total_ht', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append([f"TVA ({values.get('vat_rate', '0,00')} %)", f"{values.get('vat_amount', '0,00')} {values.get('currency', 'EUR')}"])
        financial_rows.append(["Total TTC facture", f"{values.get('total_ttc', '0,00')} {values.get('currency', 'EUR')}"])
    story.append(_table_for_pdf(["Libelle", "Valeur"], financial_rows, width=content_width))

    story.append(PageBreak())
    story.append(Paragraph("Les modalites de paiement", styles["h1"]))
    story.append(Paragraph(f"Mode de paiement : {escape(values.get('payment_method_label', '-'))}", styles["text"]))
    story.append(Paragraph(escape(values.get("payment_schedule_summary", "Paiement non planifie")), styles["text"]))
    if len(schedule) > 1:
        schedule_rows = [
            [
                str(item.get("label") or "-"),
                f"{item.get('amount_ttc', '-')}" + (f" {item.get('currency')}" if item.get("currency") else ""),
                _schedule_due_label(item),
                str(item.get("payment_method") or "-"),
            ]
            for item in schedule
        ]
        story.append(_table_for_pdf(["Echeance", "Montant", "Quand", "Type"], schedule_rows, width=content_width))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Vos options", styles["h2"]))
    story.append(Paragraph(_apply_template("{solfege_block_html}", values=values, html_keys={"solfege_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""), styles["text"]))
    story.append(Paragraph(_apply_template("{masterclass_block_html}", values=values, html_keys={"masterclass_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""), styles["text"]))
    story.append(Paragraph(_apply_template("{pass_recup_block_html}", values=values, html_keys={"pass_recup_block_html"}, html_output=True).replace("<p>", "").replace("</p>", ""), styles["text"]))

    story.append(PageBreak())
    story.append(Paragraph("Calendrier des cours", styles["h1"]))
    story.append(Paragraph(f"Resume : {escape(values.get('calendar_summary', '-'))}", styles["text"]))
    grouped: dict[str, dict[int, set[int]]] = {}
    for session in sessions:
        parsed = _session_month_day(session.get("date"))
        if parsed is None:
            continue
        month, day = parsed
        activity_label = str(session.get("activity_label") or "").strip() or "Activite"
        location_label = str(session.get("location_label") or "").strip()
        title = f"{activity_label} · {location_label}" if location_label else activity_label
        grouped.setdefault(title, {}).setdefault(month, set()).add(day)
    for idx, title in enumerate(sorted(grouped.keys()), start=1):
        month_map = grouped[title]
        count = sum(len(days) for days in month_map.values())
        story.append(Spacer(1, 5))
        story.append(Paragraph(f"Activite {idx}", styles["h3"]))
        story.append(_table_for_pdf(["Activite / lieu", "Nombre de cours"], [[title, f"{count} cours"]], width=content_width))
        sem_rows: list[list[str]] = []
        for month_label, days in _calendar_semester_rows(month_map, semester=1):
            sem_rows.append(["1er semestre", month_label, days])
        for month_label, days in _calendar_semester_rows(month_map, semester=2):
            sem_rows.append(["2e semestre", month_label, days])
        if not sem_rows:
            sem_rows.append(["-", "-", "Aucune seance"])
        story.append(_table_for_pdf(["Semestre", "Mois", "Dates de cours"], sem_rows, width=content_width))

    story.append(PageBreak())
    story.append(Paragraph("Conditions generales", styles["h1"]))
    story.append(Paragraph(escape(cgv_label or "Version non precisee"), styles["h3"]))
    for line in terms_lines:
        story.append(Paragraph(escape(line), styles["text"]))

    def _on_page(canvas_obj: Any, document: SimpleDocTemplate) -> None:
        _draw_quote_pdf_header_footer(
            canvas_obj,
            document,
            quote_number=quote.quote_number or "-",
            logo_reader=logo_reader,
        )

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()


def render_quote_pdf_from_combined_html(
    *,
    db: Session | None,
    quote: Quote,
    lines: list[QuoteLine],
    combined_html: str,
    audience: str = DEFAULT_AUDIENCE,
) -> bytes:
    # Keep signature for callers using stored combined_html snapshots.
    # The PDF itself is intentionally rebuilt from stable blocks to avoid
    # CSS/page-frame collisions that caused overlapping sections.
    _ = combined_html
    return _render_quote_pdf_blocks(db=db, quote=quote, lines=lines, audience=audience)
