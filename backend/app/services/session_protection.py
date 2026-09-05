from __future__ import annotations

import unicodedata

from app.models.catalog import CourseType, LessonFormat


def _normalized(value: str | None) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value or "").casefold()
        if not unicodedata.combining(character)
    )


def is_core_lesson_course_type(course_type: CourseType) -> bool:
    """Courses that must never be cancelled because of low attendance."""
    raw_lesson_format = getattr(course_type, "lesson_format", None)
    lesson_format = getattr(raw_lesson_format, "value", raw_lesson_format)
    if lesson_format == LessonFormat.INDIVIDUAL.value:
        return True

    code = getattr(course_type, "code", None)
    name = getattr(course_type, "name", None)
    label = f"{_normalized(code)} {_normalized(name)}"
    if "eveil musical" in label or "initiation" in label:
        return True
    if "collectif" in label and "enfant" in label:
        return True
    return code in {"PIANO_GROUP_ONSITE_1H", "PIANO_GROUP_ONLINE_1H"}
