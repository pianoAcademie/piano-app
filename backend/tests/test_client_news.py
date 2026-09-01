from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.api.routes.client_news import _article_matches_client, _client_out
from app.schemas.client_news import AdminClientNewsCreate


class ClientNewsTests(unittest.TestCase):
    def test_client_output_uses_requested_translation_with_french_fallback(self) -> None:
        now = datetime.now(timezone.utc)
        row = SimpleNamespace(
            id=uuid4(),
            title_fr="Rentrée musicale",
            title_en="Music season",
            summary_fr="Résumé français",
            summary_en=None,
            body_fr="Contenu français",
            body_en="English content",
            link_url="https://piano-academie.com",
            link_label_fr="En savoir plus",
            link_label_en="Learn more",
            is_pinned=True,
            published_at=now,
            created_at=now,
        )

        output = _client_out(row, "en")

        self.assertEqual(output.title, "Music season")
        self.assertEqual(output.summary, "Résumé français")
        self.assertEqual(output.body, "English content")
        self.assertEqual(output.link_label, "Learn more")

    def test_news_link_only_accepts_http_urls(self) -> None:
        with self.assertRaises(ValidationError):
            AdminClientNewsCreate(
                title_fr="Information",
                body_fr="Contenu",
                link_url="javascript:alert(1)",
            )

    def test_expiration_must_follow_publication(self) -> None:
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValidationError):
            AdminClientNewsCreate(
                title_fr="Information",
                body_fr="Contenu",
                status="PUBLISHED",
                published_at=now,
                expires_at=now - timedelta(minutes=1),
            )

    def test_matching_several_family_categories_returns_one_article(self) -> None:
        article = SimpleNamespace(audience_codes=["PARENTS_TEEN", "PARENTS_INITIATION"])
        self.assertTrue(_article_matches_client(article, {"PARENTS_TEEN", "PARENTS_INITIATION"}))

    def test_existing_all_clients_audience_matches_every_client(self) -> None:
        article = SimpleNamespace(audience_codes=["ALL_CLIENTS"])
        self.assertTrue(_article_matches_client(article, set()))

    def test_professor_audience_cannot_be_mixed_with_clients(self) -> None:
        with self.assertRaises(ValidationError):
            AdminClientNewsCreate(
                title_fr="Information",
                body_fr="Contenu",
                audience_codes=["PROFESSORS", "ADULT_STUDENTS"],
            )


if __name__ == "__main__":
    unittest.main()
