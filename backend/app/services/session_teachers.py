from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.catalog import CourseSession, Professor


def professor_display_name(professor: Professor | None) -> str:
    if professor is None:
        return ""
    return f"{(professor.first_name or '').strip()} {(professor.last_name or '').strip()}".strip()


def normalized_substitute_teacher_id(*, professor_id: UUID | None, substitute_teacher_id: UUID | None) -> UUID | None:
    if professor_id is not None and substitute_teacher_id == professor_id:
        return None
    return substitute_teacher_id


def effective_teacher_id_for_session(session_obj: CourseSession) -> UUID | None:
    return session_obj.substitute_teacher_id or session_obj.professor_id


def effective_teacher_filter_for_professor(*, professor_id: UUID) -> ColumnElement[bool]:
    return or_(
        CourseSession.substitute_teacher_id == professor_id,
        and_(
            CourseSession.substitute_teacher_id.is_(None),
            CourseSession.professor_id == professor_id,
        ),
    )
