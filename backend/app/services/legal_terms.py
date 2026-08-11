from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import AppSetting


LEGAL_TERMS_SETTING_KEYS = {
    "fr": "config_account_legal_terms",
    "en": "config_account_legal_terms_en",
}


@dataclass(frozen=True)
class ResolvedLegalTerms:
    language: str
    content: str
    content_hash: str
    version: str
    updated_at: datetime | None
    used_fallback: bool


def resolve_legal_terms(db: Session, requested_language: str | None) -> ResolvedLegalTerms | None:
    requested = "en" if str(requested_language or "").strip().lower().startswith("en") else "fr"
    language = requested
    setting = db.scalar(select(AppSetting).where(AppSetting.key == LEGAL_TERMS_SETTING_KEYS[language]))
    content = str(setting.value if setting is not None else "").strip()
    used_fallback = False
    if not content and requested == "en":
        language = "fr"
        setting = db.scalar(select(AppSetting).where(AppSetting.key == LEGAL_TERMS_SETTING_KEYS[language]))
        content = str(setting.value if setting is not None else "").strip()
        used_fallback = True
    if not content:
        return None

    content_hash = sha256(content.encode("utf-8")).hexdigest()
    return ResolvedLegalTerms(
        language=language,
        content=content,
        content_hash=content_hash,
        version=f"{language}-{content_hash[:12]}",
        updated_at=setting.updated_at if setting is not None else None,
        used_fallback=used_fallback,
    )
