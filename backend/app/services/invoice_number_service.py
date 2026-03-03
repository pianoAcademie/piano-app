from __future__ import annotations

from datetime import datetime, timezone
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting, LegalEntity
from app.services.invoice_documents import (
    DEFAULT_INVOICE_NUMBER_FORMAT,
    INVOICE_NUMBER_FORMAT_SETTING_KEY,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_pattern(value: str | None) -> str:
    candidate = (value or "").strip().upper()
    if not candidate:
        return DEFAULT_INVOICE_NUMBER_FORMAT
    return candidate[:120]


def _replace_sequence_token(match: re.Match[str], *, next_number: int) -> str:
    token = match.group(0)
    width = max(len(token) - 2, 1)
    return str(next_number).zfill(width)


def _sanitize_prefix(value: str | None) -> str:
    compact = "".join(ch for ch in (value or "").strip().upper() if ch.isalnum() or ch in {"_", "-"})
    if not compact:
        raise ValueError("legal_entity.invoice_prefix is required")
    return compact[:20]


def _validate_legal_entity_minimum_fields(entity: LegalEntity) -> None:
    if not (entity.name or "").strip():
        raise ValueError("legal_entity.name is required")
    country_code = (entity.country_code or "").strip().upper()
    if len(country_code) != 2 or not country_code.isalpha():
        raise ValueError("legal_entity.country_code must contain exactly 2 letters")
    if not (entity.invoice_prefix or "").strip():
        raise ValueError("legal_entity.invoice_prefix is required")


def _pattern_for_entity(*, global_pattern: str, invoice_prefix: str) -> str:
    pattern = _normalize_pattern(global_pattern)
    if "%PREFIX%" in pattern:
        candidate = pattern.replace("%PREFIX%", invoice_prefix)
    else:
        first_token_index = pattern.find("%")
        if first_token_index > 0:
            candidate = f"{invoice_prefix}{pattern[first_token_index:]}"
        else:
            candidate = f"{invoice_prefix}-%YYYY%-%NNNN%"
    if "%N" not in candidate:
        candidate = f"{candidate}-%NNNN%"
    return candidate[:120]


def _render_invoice_number(*, pattern: str, issued_at: datetime, next_number: int) -> str:
    rendered = pattern
    rendered = rendered.replace("%YYYY%", issued_at.strftime("%Y"))
    rendered = rendered.replace("%YY%", issued_at.strftime("%y"))
    rendered = rendered.replace("%MM%", issued_at.strftime("%m"))
    rendered = rendered.replace("%DD%", issued_at.strftime("%d"))
    rendered = re.sub(
        r"%N+%",
        lambda match: _replace_sequence_token(match, next_number=next_number),
        rendered,
    )
    if "%N" in rendered:
        rendered = rendered.replace("%N", str(next_number))
    return rendered[:120]


class InvoiceNumberService:
    @staticmethod
    def allocate_invoice_number(
        db: Session,
        *,
        legal_entity_id: UUID,
        issued_at: datetime | None = None,
    ) -> str:
        effective_issued_at = issued_at or _utcnow()
        legal_entity = db.scalar(
            select(LegalEntity).where(LegalEntity.id == legal_entity_id).with_for_update()
        )
        if legal_entity is None:
            raise ValueError(f"Unknown legal entity id: {legal_entity_id}")
        _validate_legal_entity_minimum_fields(legal_entity)

        pattern_row = db.scalar(
            select(AppSetting).where(AppSetting.key == INVOICE_NUMBER_FORMAT_SETTING_KEY)
        )
        global_pattern = _normalize_pattern(pattern_row.value if pattern_row is not None else None)
        invoice_prefix = _sanitize_prefix(legal_entity.invoice_prefix)
        sequence_value = max(1, int(legal_entity.invoice_next_number or 1))
        pattern = _pattern_for_entity(global_pattern=global_pattern, invoice_prefix=invoice_prefix)
        invoice_number = _render_invoice_number(
            pattern=pattern,
            issued_at=effective_issued_at,
            next_number=sequence_value,
        )

        legal_entity.invoice_next_number = sequence_value + 1
        legal_entity.updated_at = _utcnow()
        db.add(legal_entity)
        return invoice_number
