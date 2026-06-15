from types import SimpleNamespace

from app.services.quotes.quote_documents import (
    _localized_english_text_fragments,
    _localized_location_label,
    _planning_activity_display_label,
    _quote_line_display_title,
    _weekday_label_from_fields,
)


def test_translates_teen_adult_group_activity_for_english_quote() -> None:
    assert (
        _planning_activity_display_label(
            {"activity_label": "Cours collectifs ado/adultes"},
            language="en",
        )
        == "Teen/adult group lessons"
    )


def test_translates_teen_adult_group_quote_line_for_english_quote() -> None:
    line = SimpleNamespace(title="Cours collectifs ado/adultes")
    assert _quote_line_display_title(line, language="en") == "Teen/adult group lessons"


def test_keeps_french_activity_label_for_french_quote() -> None:
    assert (
        _planning_activity_display_label(
            {"activity_label": "Cours collectifs ado/adultes"},
            language="fr",
        )
        == "Cours collectifs ado/adultes"
    )


def test_translates_french_weekday_label_for_english_quote() -> None:
    assert _weekday_label_from_fields("Lundi", None, language="en") == "Monday"


def test_translates_french_location_label_for_english_quote() -> None:
    assert _localized_location_label("Rue Richelieu", language="en") == "Richelieu Street"


def test_translates_terms_fragments_for_english_quote() -> None:
    source = "Conditions générales de vente et d’inscription 2026–2027\nPour finaliser votre inscription"
    translated = _localized_english_text_fragments(source, language="en")
    assert "General terms of sale and enrollment 2026–2027" in translated
    assert "To finalize your enrollment" in translated


def test_keeps_terms_fragments_for_french_quote() -> None:
    source = "Conditions générales de vente et d’inscription"
    assert _localized_english_text_fragments(source, language="fr") == source
