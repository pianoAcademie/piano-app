from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import json
from typing import Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import CourseType
from app.models.external_content import (
    ContentAccessRule,
    CourseTypeContentMapping,
    ExternalContentCourse,
    ExternalContentLesson,
    ExternalContentProvider,
    ExternalContentSection,
    ExternalContentStatus,
)
from app.models.ops import AppSetting


WORDPRESS_LEARNDASH_BASE_URL_SETTING_KEY = "external_content.wordpress_learndash.base_url"
WORDPRESS_LEARNDASH_COURSES_ENDPOINT_SETTING_KEY = "external_content.wordpress_learndash.courses_endpoint"
WORDPRESS_LEARNDASH_BEARER_TOKEN_SETTING_KEY = "external_content.wordpress_learndash.bearer_token"
WORDPRESS_LEARNDASH_TIMEOUT_SECONDS_SETTING_KEY = "external_content.wordpress_learndash.timeout_seconds"
DEFAULT_WORDPRESS_LEARNDASH_COURSES_PATH = "/wp-json/piano/v1/courses"


@dataclass(slots=True)
class ExternalLessonPayload:
    external_id: str
    title: str
    slug: str | None = None
    position: int = 0
    summary: str | None = None
    content_html: str | None = None
    video_url: str | None = None
    resource_url: str | None = None
    status: ExternalContentStatus = ExternalContentStatus.PUBLISHED
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ExternalSectionPayload:
    external_id: str
    title: str
    position: int = 0
    metadata_json: dict[str, object] = field(default_factory=dict)
    lessons: list[ExternalLessonPayload] = field(default_factory=list)


@dataclass(slots=True)
class ExternalCoursePayload:
    external_id: str
    title: str
    slug: str | None = None
    summary: str | None = None
    level_code: str | None = None
    status: ExternalContentStatus = ExternalContentStatus.PUBLISHED
    cover_image_url: str | None = None
    metadata_json: dict[str, object] = field(default_factory=dict)
    sections: list[ExternalSectionPayload] = field(default_factory=list)
    lessons: list[ExternalLessonPayload] = field(default_factory=list)


@dataclass(slots=True)
class ExternalContentSyncSummary:
    provider: ExternalContentProvider
    fetched_at: datetime
    courses_seen: int = 0
    courses_created: int = 0
    courses_updated: int = 0
    sections_seen: int = 0
    sections_created: int = 0
    sections_updated: int = 0
    sections_deleted: int = 0
    lessons_seen: int = 0
    lessons_created: int = 0
    lessons_updated: int = 0
    lessons_deleted: int = 0


def _setting_value(db: Session, key: str) -> str | None:
    return db.scalar(select(AppSetting.value).where(AppSetting.key == key))


def _string_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple, set)):
        return None
    if isinstance(value, str):
        normalized = html.unescape(value).replace("\ufffc", "").replace("\xa0", " ").strip()
        return normalized or None
    normalized = html.unescape(str(value)).replace("\ufffc", "").replace("\xa0", " ").strip()
    return normalized or None


def _int_value(value: object | None, *, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dict_value(value: object | None) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list_value(value: object | None) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _first_value(payload: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _nested_string(payload: dict[str, object], key: str, nested_key: str) -> str | None:
    raw = payload.get(key)
    if isinstance(raw, dict):
        return _string_value(raw.get(nested_key))
    return None


def _normalized_status(value: object | None) -> ExternalContentStatus:
    normalized = _string_value(value)
    if not normalized:
        return ExternalContentStatus.PUBLISHED
    normalized = normalized.upper()
    if normalized in {"PUBLISH", "PUBLISHED", "PUBLIC"}:
        return ExternalContentStatus.PUBLISHED
    if normalized in {"DRAFT", "PRIVATE"}:
        return ExternalContentStatus.DRAFT
    if normalized in {"ARCHIVED", "TRASH"}:
        return ExternalContentStatus.ARCHIVED
    return ExternalContentStatus.PUBLISHED


def _sanitized_metadata(payload: dict[str, object], *, drop_keys: Iterable[str]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key not in set(drop_keys)
    }


def _lesson_payload(raw: dict[str, object], *, default_position: int) -> ExternalLessonPayload:
    external_id = _string_value(_first_value(raw, "external_id", "id", "lesson_id", "wp_id"))
    title = _string_value(_first_value(raw, "title", "name", "label"))
    if not external_id or not title:
        raise ValueError("Each lesson payload must include an id and a title")
    raw_content = _first_value(raw, "content_html", "content", "html")
    content_html = _string_value(raw_content) or _nested_string(raw, "content", "rendered")
    raw_video = _first_value(raw, "video_url", "video")
    video_url = _string_value(raw_video) or _nested_string(raw, "video", "url")
    raw_resource = _first_value(raw, "resource_url", "download_url", "resource")
    resource_url = _string_value(raw_resource) or _nested_string(raw, "resource", "url")
    return ExternalLessonPayload(
        external_id=external_id,
        title=title,
        slug=_string_value(_first_value(raw, "slug")),
        position=_int_value(_first_value(raw, "position", "order", "menu_order"), default=default_position),
        summary=_string_value(_first_value(raw, "summary", "excerpt", "description")),
        content_html=content_html,
        video_url=video_url,
        resource_url=resource_url,
        status=_normalized_status(_first_value(raw, "status")),
        metadata_json=_sanitized_metadata(raw, drop_keys={"content_html", "content", "html"}),
    )


def _section_payload(raw: dict[str, object], *, default_position: int) -> ExternalSectionPayload:
    external_id = _string_value(_first_value(raw, "external_id", "id", "section_id", "module_id"))
    title = _string_value(_first_value(raw, "title", "name", "label"))
    if not external_id or not title:
        raise ValueError("Each section payload must include an id and a title")
    raw_lessons = _list_value(_first_value(raw, "lessons", "items"))
    return ExternalSectionPayload(
        external_id=external_id,
        title=title,
        position=_int_value(_first_value(raw, "position", "order", "menu_order"), default=default_position),
        metadata_json=_sanitized_metadata(raw, drop_keys={"lessons", "items"}),
        lessons=[
            _lesson_payload(_dict_value(raw_lesson), default_position=index)
            for index, raw_lesson in enumerate(raw_lessons)
            if isinstance(raw_lesson, dict)
        ],
    )


def normalize_wordpress_learndash_catalog_payload(payload: object) -> list[ExternalCoursePayload]:
    if payload is None:
        return []
    if isinstance(payload, list):
        raw_courses = payload
    elif isinstance(payload, dict):
        raw_courses = _list_value(payload.get("courses")) if isinstance(payload.get("courses"), list) else [payload]
    else:
        raise ValueError("Unsupported WordPress/LearnDash payload format")

    normalized_courses: list[ExternalCoursePayload] = []
    for index, raw_course in enumerate(raw_courses):
        if not isinstance(raw_course, dict):
            continue
        external_id = _string_value(_first_value(raw_course, "external_id", "id", "course_id", "wp_id"))
        title = _string_value(_first_value(raw_course, "title", "name", "label"))
        if not external_id or not title:
            raise ValueError("Each course payload must include an id and a title")
        raw_sections = _list_value(_first_value(raw_course, "sections", "modules", "outline_sections"))
        raw_standalone_lessons = _list_value(_first_value(raw_course, "standalone_lessons"))
        if not raw_standalone_lessons and not raw_sections:
            raw_standalone_lessons = _list_value(_first_value(raw_course, "lessons"))
        course = ExternalCoursePayload(
            external_id=external_id,
            title=title,
            slug=_string_value(_first_value(raw_course, "slug")),
            summary=_string_value(_first_value(raw_course, "summary", "excerpt", "description")),
            level_code=_string_value(_first_value(raw_course, "level_code", "level", "course_level", "niveau")),
            status=_normalized_status(_first_value(raw_course, "status")),
            cover_image_url=_string_value(_first_value(raw_course, "cover_image_url", "cover_url", "featured_image_url")),
            metadata_json=_sanitized_metadata(
                raw_course,
                drop_keys={"sections", "modules", "outline_sections", "lessons", "standalone_lessons"},
            ),
            sections=[
                _section_payload(_dict_value(raw_section), default_position=section_index)
                for section_index, raw_section in enumerate(raw_sections)
                if isinstance(raw_section, dict)
            ],
            lessons=[
                _lesson_payload(_dict_value(raw_lesson), default_position=lesson_index)
                for lesson_index, raw_lesson in enumerate(raw_standalone_lessons)
                if isinstance(raw_lesson, dict)
            ],
        )
        normalized_courses.append(course)
    return normalized_courses


def resolve_wordpress_learndash_sync_endpoint(
    db: Session,
    *,
    default_path: str = DEFAULT_WORDPRESS_LEARNDASH_COURSES_PATH,
) -> tuple[str, str | None, int]:
    explicit_endpoint = _setting_value(db, WORDPRESS_LEARNDASH_COURSES_ENDPOINT_SETTING_KEY)
    bearer_token = _setting_value(db, WORDPRESS_LEARNDASH_BEARER_TOKEN_SETTING_KEY)
    timeout_seconds = _int_value(_setting_value(db, WORDPRESS_LEARNDASH_TIMEOUT_SECONDS_SETTING_KEY), default=20)
    if explicit_endpoint:
        return explicit_endpoint, bearer_token, max(5, timeout_seconds)
    base_url = _setting_value(db, WORDPRESS_LEARNDASH_BASE_URL_SETTING_KEY)
    if not base_url:
        raise ValueError(
            "WordPress/LearnDash sync endpoint is not configured. Set either the explicit endpoint or the base URL in app_settings."
        )
    return f"{base_url.rstrip('/')}{default_path}", bearer_token, max(5, timeout_seconds)


def _fetch_json(url: str, *, bearer_token: str | None, timeout_seconds: int) -> object:
    headers = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:  # pragma: no cover - network error path
        raise RuntimeError(f"WordPress sync failed with HTTP {exc.code}") from exc
    except URLError as exc:  # pragma: no cover - network error path
        raise RuntimeError(f"WordPress sync failed: {exc.reason}") from exc


def _apply_changes(row: object, **updates: object) -> bool:
    changed = False
    for key, value in updates.items():
        if getattr(row, key) != value:
            setattr(row, key, value)
            changed = True
    return changed


def _upsert_course_payload(
    db: Session,
    *,
    payload: ExternalCoursePayload,
    provider: ExternalContentProvider,
    synced_at: datetime,
    summary: ExternalContentSyncSummary,
) -> ExternalContentCourse:
    summary.courses_seen += 1
    row = db.scalar(
        select(ExternalContentCourse).where(
            ExternalContentCourse.provider == provider,
            ExternalContentCourse.external_id == payload.external_id,
        )
    )
    created = row is None
    if row is None:
        row = ExternalContentCourse(
            provider=provider,
            external_id=payload.external_id,
            title=payload.title,
            slug=payload.slug,
            summary=payload.summary,
            level_code=payload.level_code,
            status=payload.status,
            cover_image_url=payload.cover_image_url,
            metadata_json=payload.metadata_json,
            last_synced_at=synced_at,
        )
        db.add(row)
        db.flush()
        summary.courses_created += 1
    else:
        if _apply_changes(
            row,
            title=payload.title,
            slug=payload.slug,
            summary=payload.summary,
            level_code=payload.level_code,
            status=payload.status,
            cover_image_url=payload.cover_image_url,
            metadata_json=payload.metadata_json,
            last_synced_at=synced_at,
            updated_at=synced_at,
        ):
            summary.courses_updated += 1
    return row


def _upsert_nested_sections_and_lessons(
    db: Session,
    *,
    course_row: ExternalContentCourse,
    payload: ExternalCoursePayload,
    synced_at: datetime,
    summary: ExternalContentSyncSummary,
) -> None:
    existing_sections = {
        row.external_id: row
        for row in db.scalars(select(ExternalContentSection).where(ExternalContentSection.course_id == course_row.id)).all()
    }
    incoming_section_ids: set[str] = set()
    section_rows_by_external_id: dict[str, ExternalContentSection] = {}

    for section_payload in payload.sections:
        summary.sections_seen += 1
        incoming_section_ids.add(section_payload.external_id)
        section_row = existing_sections.get(section_payload.external_id)
        if section_row is None:
            section_row = ExternalContentSection(
                course_id=course_row.id,
                external_id=section_payload.external_id,
                title=section_payload.title,
                position=section_payload.position,
                metadata_json=section_payload.metadata_json,
            )
            db.add(section_row)
            summary.sections_created += 1
        else:
            if _apply_changes(
                section_row,
                title=section_payload.title,
                position=section_payload.position,
                metadata_json=section_payload.metadata_json,
                updated_at=synced_at,
            ):
                summary.sections_updated += 1
        section_rows_by_external_id[section_payload.external_id] = section_row

    db.flush()

    existing_lessons = {
        row.external_id: row
        for row in db.scalars(select(ExternalContentLesson).where(ExternalContentLesson.course_id == course_row.id)).all()
    }
    incoming_lesson_ids: set[str] = set()

    def upsert_lesson(lesson_payload: ExternalLessonPayload, *, section_id: UUID | None) -> None:
        summary.lessons_seen += 1
        incoming_lesson_ids.add(lesson_payload.external_id)
        lesson_row = existing_lessons.get(lesson_payload.external_id)
        if lesson_row is None:
            lesson_row = ExternalContentLesson(
                course_id=course_row.id,
                section_id=section_id,
                external_id=lesson_payload.external_id,
                slug=lesson_payload.slug,
                title=lesson_payload.title,
                position=lesson_payload.position,
                summary=lesson_payload.summary,
                content_html=lesson_payload.content_html,
                video_url=lesson_payload.video_url,
                resource_url=lesson_payload.resource_url,
                status=lesson_payload.status,
                metadata_json=lesson_payload.metadata_json,
                last_synced_at=synced_at,
            )
            db.add(lesson_row)
            summary.lessons_created += 1
        else:
            if _apply_changes(
                lesson_row,
                section_id=section_id,
                slug=lesson_payload.slug,
                title=lesson_payload.title,
                position=lesson_payload.position,
                summary=lesson_payload.summary,
                content_html=lesson_payload.content_html,
                video_url=lesson_payload.video_url,
                resource_url=lesson_payload.resource_url,
                status=lesson_payload.status,
                metadata_json=lesson_payload.metadata_json,
                last_synced_at=synced_at,
                updated_at=synced_at,
            ):
                summary.lessons_updated += 1

    for section_payload in payload.sections:
        section_row = section_rows_by_external_id[section_payload.external_id]
        for lesson_payload in section_payload.lessons:
            upsert_lesson(lesson_payload, section_id=section_row.id)

    for lesson_payload in payload.lessons:
        upsert_lesson(lesson_payload, section_id=None)

    for external_id, lesson_row in existing_lessons.items():
        if external_id not in incoming_lesson_ids:
            db.delete(lesson_row)
            summary.lessons_deleted += 1

    for external_id, section_row in existing_sections.items():
        if external_id not in incoming_section_ids:
            db.delete(section_row)
            summary.sections_deleted += 1


def sync_wordpress_learndash_catalog(
    db: Session,
    *,
    payload: object | None = None,
    endpoint_url: str | None = None,
    bearer_token: str | None = None,
    timeout_seconds: int | None = None,
) -> ExternalContentSyncSummary:
    if payload is None:
        if endpoint_url is None:
            endpoint_url, bearer_token, resolved_timeout = resolve_wordpress_learndash_sync_endpoint(db)
        else:
            resolved_timeout = max(5, timeout_seconds or 20)
        payload = _fetch_json(endpoint_url, bearer_token=bearer_token, timeout_seconds=resolved_timeout)

    normalized_courses = normalize_wordpress_learndash_catalog_payload(payload)
    synced_at = datetime.now(timezone.utc)
    summary = ExternalContentSyncSummary(
        provider=ExternalContentProvider.WORDPRESS_LEARNDASH,
        fetched_at=synced_at,
    )
    for course_payload in normalized_courses:
        course_row = _upsert_course_payload(
            db,
            payload=course_payload,
            provider=ExternalContentProvider.WORDPRESS_LEARNDASH,
            synced_at=synced_at,
            summary=summary,
        )
        _upsert_nested_sections_and_lessons(
            db,
            course_row=course_row,
            payload=course_payload,
            synced_at=synced_at,
            summary=summary,
        )
    db.flush()
    return summary


def upsert_course_type_content_mapping(
    db: Session,
    *,
    course_type_id: UUID,
    content_course_id: UUID,
    access_rule: ContentAccessRule = ContentAccessRule.ACTIVE_ENROLLMENT,
    sort_order: int = 0,
    active: bool = True,
) -> CourseTypeContentMapping:
    mapping = db.scalar(
        select(CourseTypeContentMapping).where(
            CourseTypeContentMapping.course_type_id == course_type_id,
            CourseTypeContentMapping.content_course_id == content_course_id,
        )
    )
    now = datetime.now(timezone.utc)
    if mapping is None:
        mapping = CourseTypeContentMapping(
            course_type_id=course_type_id,
            content_course_id=content_course_id,
            access_rule=access_rule,
            sort_order=sort_order,
            active=active,
            created_at=now,
            updated_at=now,
        )
        db.add(mapping)
    else:
        _apply_changes(
            mapping,
            access_rule=access_rule,
            sort_order=sort_order,
            active=active,
            updated_at=now,
        )
    db.flush()
    return mapping


def replace_course_type_content_mappings(
    db: Session,
    *,
    course_type_id: UUID,
    content_course_ids: Sequence[UUID],
    access_rule: ContentAccessRule | str = ContentAccessRule.ACTIVE_ENROLLMENT,
) -> list[CourseTypeContentMapping]:
    validate_course_type_exists(db, course_type_id)
    try:
        normalized_access_rule = (
            access_rule if isinstance(access_rule, ContentAccessRule) else ContentAccessRule(str(access_rule).strip().upper())
        )
    except ValueError as exc:
        raise ValueError("Unknown content access_rule") from exc

    normalized_ids: list[UUID] = []
    seen_ids: set[UUID] = set()
    for value in content_course_ids:
        if value in seen_ids:
            continue
        seen_ids.add(value)
        normalized_ids.append(value)

    if normalized_ids:
        existing_courses = db.scalars(select(ExternalContentCourse).where(ExternalContentCourse.id.in_(normalized_ids))).all()
        existing_course_ids = {row.id for row in existing_courses}
        missing_course_ids = [str(value) for value in normalized_ids if value not in existing_course_ids]
        if missing_course_ids:
            raise ValueError(f"Unknown content_course_id(s): {', '.join(missing_course_ids)}")

    existing_mappings = db.scalars(
        select(CourseTypeContentMapping).where(CourseTypeContentMapping.course_type_id == course_type_id)
    ).all()
    desired_ids = set(normalized_ids)

    for row in existing_mappings:
        if row.content_course_id not in desired_ids:
            db.delete(row)

    ordered_rows: list[CourseTypeContentMapping] = []
    for index, content_course_id in enumerate(normalized_ids):
        ordered_rows.append(
            upsert_course_type_content_mapping(
                db,
                course_type_id=course_type_id,
                content_course_id=content_course_id,
                access_rule=normalized_access_rule,
                sort_order=index,
                active=True,
            )
        )

    db.flush()
    return ordered_rows


def list_content_courses_for_course_type_ids(
    db: Session,
    course_type_ids: Sequence[UUID],
    *,
    active_only: bool = True,
) -> list[ExternalContentCourse]:
    normalized_ids = [value for value in course_type_ids if value is not None]
    if not normalized_ids:
        return []
    stmt = (
        select(ExternalContentCourse)
        .join(
            CourseTypeContentMapping,
            CourseTypeContentMapping.content_course_id == ExternalContentCourse.id,
        )
        .where(CourseTypeContentMapping.course_type_id.in_(normalized_ids))
        .order_by(CourseTypeContentMapping.sort_order.asc(), ExternalContentCourse.title.asc())
    )
    if active_only:
        stmt = stmt.where(CourseTypeContentMapping.active.is_(True))
    ordered_rows = list(db.scalars(stmt).all())
    deduped_rows: list[ExternalContentCourse] = []
    seen_ids: set[UUID] = set()
    for row in ordered_rows:
        if row.id in seen_ids:
            continue
        seen_ids.add(row.id)
        deduped_rows.append(row)
    return deduped_rows


def list_content_course_mappings_for_course_type(
    db: Session,
    *,
    course_type_id: UUID,
    active_only: bool = True,
) -> list[tuple[CourseTypeContentMapping, ExternalContentCourse]]:
    stmt = (
        select(CourseTypeContentMapping, ExternalContentCourse)
        .join(ExternalContentCourse, ExternalContentCourse.id == CourseTypeContentMapping.content_course_id)
        .where(CourseTypeContentMapping.course_type_id == course_type_id)
        .order_by(CourseTypeContentMapping.sort_order.asc(), ExternalContentCourse.title.asc())
    )
    if active_only:
        stmt = stmt.where(CourseTypeContentMapping.active.is_(True))
    return [(mapping, course) for mapping, course in db.execute(stmt).all()]


def validate_course_type_exists(db: Session, course_type_id: UUID) -> CourseType:
    row = db.scalar(select(CourseType).where(CourseType.id == course_type_id))
    if row is None:
        raise ValueError("Unknown course_type_id")
    return row
