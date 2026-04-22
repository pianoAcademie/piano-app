from __future__ import annotations

from collections.abc import Mapping

DEFAULT_LANGUAGE = "fr"
SUPPORTED_LANGUAGES = ("fr", "en")

LocalizedTextMap = dict[str, str]


def normalize_language(value: str | None, *, fallback: str = DEFAULT_LANGUAGE, allow_none: bool = False) -> str | None:
    candidate = str(value or "").strip().lower()
    if candidate in SUPPORTED_LANGUAGES:
        return candidate
    if allow_none:
        return None
    return fallback


def normalize_text(value: object, *, max_length: int | None = None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if max_length is not None and len(text) > max_length:
        return text[:max_length]
    return text


def normalize_translations(raw: Mapping[str, object] | None, *, max_length: int | None = None) -> LocalizedTextMap:
    if not isinstance(raw, Mapping):
        return {}

    out: LocalizedTextMap = {}
    for raw_language, raw_value in raw.items():
        language = normalize_language(str(raw_language), allow_none=True)
        if language is None:
            continue
        text = normalize_text(raw_value, max_length=max_length)
        if text is None:
            continue
        out[language] = text
    return out


def build_translations_payload(
    base_value: object,
    translations: Mapping[str, object] | None,
    *,
    max_length: int | None = None,
) -> LocalizedTextMap:
    out = normalize_translations(translations, max_length=max_length)
    base_text = normalize_text(base_value, max_length=max_length)
    if base_text is not None:
        out[DEFAULT_LANGUAGE] = base_text
    return dict(sorted(out.items()))


def translations_for_storage(
    base_value: object,
    translations: Mapping[str, object] | None,
    *,
    max_length: int | None = None,
) -> LocalizedTextMap:
    out = normalize_translations(translations, max_length=max_length)
    base_text = normalize_text(base_value, max_length=max_length)
    if base_text is not None and out.get(DEFAULT_LANGUAGE) == base_text:
        out.pop(DEFAULT_LANGUAGE, None)
    return out


def resolve_localized_text(
    base_value: object,
    translations: Mapping[str, object] | None,
    *,
    language: str | None = None,
    max_length: int | None = None,
) -> str | None:
    normalized_language = normalize_language(language)
    normalized_translations = normalize_translations(translations, max_length=max_length)
    base_text = normalize_text(base_value, max_length=max_length)

    if normalized_language == DEFAULT_LANGUAGE and base_text is not None:
        return base_text

    translated = normalized_translations.get(normalized_language)
    if translated is not None:
        return translated

    if base_text is not None:
        return base_text

    fallback = normalized_translations.get(DEFAULT_LANGUAGE)
    if fallback is not None:
        return fallback

    for value in normalized_translations.values():
        return value
    return None
