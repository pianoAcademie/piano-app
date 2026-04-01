from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.models.external_content import ExternalContentStatus
from app.services.external_content import (
    DEFAULT_WORDPRESS_LEARNDASH_COURSES_PATH,
    normalize_wordpress_learndash_catalog_payload,
    resolve_wordpress_learndash_sync_endpoint,
)


class _FakeSettingsSession:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values


class ExternalContentTests(unittest.TestCase):
    def test_normalize_catalog_payload_with_sections_and_lessons(self) -> None:
        payload = {
            "courses": [
                {
                    "id": 101,
                    "slug": "solfege-niveau-1",
                    "title": "Solfege niveau 1",
                    "level_code": "SOLFEGE_N1",
                    "status": "publish",
                    "cover_image_url": "https://example.com/covers/n1.jpg",
                    "sections": [
                        {
                            "id": "section-a",
                            "title": "Lecture",
                            "position": 1,
                            "lessons": [
                                {
                                    "id": "lesson-1",
                                    "title": "Les notes",
                                    "slug": "les-notes",
                                    "content": {"rendered": "<p>Do Re Mi</p>"},
                                    "video_url": "https://example.com/videos/lesson-1.mp4",
                                }
                            ],
                        }
                    ],
                    "standalone_lessons": [
                        {
                            "id": "lesson-standalone",
                            "title": "Exercice 1",
                            "summary": "Travail de la cle de sol",
                        }
                    ],
                }
            ]
        }

        courses = normalize_wordpress_learndash_catalog_payload(payload)

        self.assertEqual(len(courses), 1)
        course = courses[0]
        self.assertEqual(course.external_id, "101")
        self.assertEqual(course.level_code, "SOLFEGE_N1")
        self.assertEqual(course.status, ExternalContentStatus.PUBLISHED)
        self.assertEqual(len(course.sections), 1)
        self.assertEqual(len(course.lessons), 1)
        self.assertEqual(course.sections[0].external_id, "section-a")
        self.assertEqual(course.sections[0].lessons[0].content_html, "<p>Do Re Mi</p>")
        self.assertEqual(course.sections[0].lessons[0].video_url, "https://example.com/videos/lesson-1.mp4")
        self.assertEqual(course.lessons[0].title, "Exercice 1")

    def test_normalize_single_course_payload_without_courses_wrapper(self) -> None:
        payload = {
            "external_id": "course-solfege-2",
            "title": "Solfege niveau 2",
            "lessons": [
                {"external_id": "lesson-2", "title": "Le rythme", "status": "draft"},
            ],
        }

        courses = normalize_wordpress_learndash_catalog_payload(payload)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].external_id, "course-solfege-2")
        self.assertEqual(courses[0].lessons[0].status, ExternalContentStatus.DRAFT)

    def test_normalize_catalog_payload_decodes_html_entities(self) -> None:
        payload = {
            "courses": [
                {
                    "id": "course-1",
                    "title": "Solfège débutant &#8211; Période 1",
                    "summary": "Bienvenue &amp; bon travail",
                    "sections": [
                        {
                            "id": "section-1",
                            "title": "Débutant &#8211; leçon n°1",
                            "lessons": [
                                {
                                    "id": "lesson-1",
                                    "title": "Cours n°1 &#8211; Clef de fa",
                                    "summary": "&lt;br /&gt;",
                                    "content_html": "<iframe src='http://www.cloudlearning.fr/demo'></iframe>\ufffc",
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        courses = normalize_wordpress_learndash_catalog_payload(payload)

        self.assertEqual(courses[0].title, "Solfège débutant – Période 1")
        self.assertEqual(courses[0].summary, "Bienvenue & bon travail")
        self.assertEqual(courses[0].sections[0].title, "Débutant – leçon n°1")
        self.assertEqual(courses[0].sections[0].lessons[0].title, "Cours n°1 – Clef de fa")
        self.assertEqual(courses[0].sections[0].lessons[0].summary, "<br />")
        self.assertNotIn("\ufffc", courses[0].sections[0].lessons[0].content_html or "")

    def test_resolve_sync_endpoint_prefers_explicit_endpoint(self) -> None:
        fake_db = _FakeSettingsSession({})
        values = {
            "external_content.wordpress_learndash.courses_endpoint": "https://wp.example.com/wp-json/piano/v1/courses",
            "external_content.wordpress_learndash.bearer_token": "secret",
            "external_content.wordpress_learndash.timeout_seconds": "45",
        }
        with patch("app.services.external_content._setting_value", side_effect=lambda _db, key: values.get(key)):
            endpoint, bearer_token, timeout_seconds = resolve_wordpress_learndash_sync_endpoint(fake_db)

        self.assertEqual(endpoint, "https://wp.example.com/wp-json/piano/v1/courses")
        self.assertEqual(bearer_token, "secret")
        self.assertEqual(timeout_seconds, 45)

    def test_resolve_sync_endpoint_builds_from_base_url(self) -> None:
        fake_db = _FakeSettingsSession({})
        values = {
            "external_content.wordpress_learndash.base_url": "https://wp.example.com/",
        }
        with patch("app.services.external_content._setting_value", side_effect=lambda _db, key: values.get(key)):
            endpoint, bearer_token, timeout_seconds = resolve_wordpress_learndash_sync_endpoint(fake_db)

        self.assertEqual(endpoint, f"https://wp.example.com{DEFAULT_WORDPRESS_LEARNDASH_COURSES_PATH}")
        self.assertIsNone(bearer_token)
        self.assertEqual(timeout_seconds, 20)


if __name__ == "__main__":
    unittest.main()
