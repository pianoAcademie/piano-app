from types import SimpleNamespace

from app.services.quotes.quote_documents import (
    _calendar_group_heading,
    _localized_catalog_text,
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


def test_translates_catalog_product_labels_for_english_quote() -> None:
    assert _quote_line_display_title(SimpleNamespace(title="Solfège - niveau 2"), language="en") == "Music theory - Level 2"
    assert (
        _quote_line_display_title(SimpleNamespace(title="Cahier de solfège de niveau 2"), language="en")
        == "Music theory workbook - Level 2"
    )
    assert _quote_line_display_title(SimpleNamespace(title="Partitions Ados"), language="en") == "Teen sheet music"
    assert _quote_line_display_title(SimpleNamespace(title="Kit Ado"), language="en") == "Teen kit"


def test_translates_catalog_descriptions_for_english_quote() -> None:
    assert _localized_catalog_text("Avec son cahier de travail", language="en") == "Includes its workbook"
    assert (
        _localized_catalog_text("Frais de dossier\nCours de contrôle x 2", language="en")
        == "Enrollment fee\nAssessment lessons x 2"
    )


def test_keeps_catalog_labels_for_french_quote() -> None:
    assert _quote_line_display_title(SimpleNamespace(title="Cahier de solfège de niveau 2"), language="fr") == "Cahier de solfège de niveau 2"
    assert _localized_catalog_text("Frais de dossier\nCours de contrôle x 2", language="fr") == "Frais de dossier\nCours de contrôle x 2"


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
    assert _localized_location_label("Rue de Richelieu", language="en") == "Richelieu Street"


def test_translates_calendar_group_heading_for_english_quote() -> None:
    assert (
        _calendar_group_heading("Cours collectifs ado/adultes · Rue de Richelieu", 1, language="en")
        == "Teen/adult group lessons · Richelieu Street"
    )


def test_translates_terms_fragments_for_english_quote() -> None:
    source = "Conditions générales de vente et d’inscription 2026–2027\nPour finaliser votre inscription"
    translated = _localized_english_text_fragments(source, language="en")
    assert "General terms of sale and enrollment 2026–2027" in translated
    assert "To finalize your enrollment" in translated


def test_keeps_terms_fragments_for_french_quote() -> None:
    source = "Conditions générales de vente et d’inscription"
    assert _localized_english_text_fragments(source, language="fr") == source
