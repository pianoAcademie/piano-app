from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.legal_terms import resolve_legal_terms


def _setting(value: str, *, updated_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(value=value, updated_at=updated_at or datetime(2026, 8, 11, tzinfo=timezone.utc))


def test_resolve_french_legal_terms() -> None:
    db = MagicMock()
    db.scalar.return_value = _setting("## CGV\n\nTexte français")

    resolved = resolve_legal_terms(db, "fr-FR")

    assert resolved is not None
    assert resolved.language == "fr"
    assert resolved.content == "## CGV\n\nTexte français"
    assert resolved.version.startswith("fr-")
    assert len(resolved.content_hash) == 64
    assert resolved.used_fallback is False
    db.scalar.assert_called_once()


def test_resolve_english_legal_terms() -> None:
    db = MagicMock()
    db.scalar.return_value = _setting("## Terms\n\nEnglish text")

    resolved = resolve_legal_terms(db, "en")

    assert resolved is not None
    assert resolved.language == "en"
    assert resolved.content == "## Terms\n\nEnglish text"
    assert resolved.used_fallback is False
    db.scalar.assert_called_once()


def test_english_terms_fall_back_to_french() -> None:
    db = MagicMock()
    db.scalar.side_effect = [_setting(""), _setting("Texte français")]

    resolved = resolve_legal_terms(db, "en-GB")

    assert resolved is not None
    assert resolved.language == "fr"
    assert resolved.content == "Texte français"
    assert resolved.used_fallback is True
    assert db.scalar.call_count == 2


def test_resolve_legal_terms_returns_none_when_not_configured() -> None:
    db = MagicMock()
    db.scalar.return_value = None

    assert resolve_legal_terms(db, "fr") is None
