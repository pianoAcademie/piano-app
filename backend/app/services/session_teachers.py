from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, delete, exists, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.catalog import CourseSession, CourseSessionProfessor, CourseType, Professor


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


def is_masterclass_course_type(course_type: CourseType | None) -> bool:
    if course_type is None:
        return False
    searchable = " ".join(
        str(value or "").strip().casefold()
        for value in (course_type.code, course_type.service_code, course_type.name)
    )
    return "masterclass" in searchable or "master class" in searchable


def normalize_professor_ids_for_course_type(
    *,
    course_type: CourseType,
    professor_id: UUID | None,
    professor_ids: list[UUID] | None,
) -> list[UUID]:
    requested = list(professor_ids or ([] if professor_id is None else [professor_id]))
    if professor_id is not None and professor_id not in requested:
        requested.insert(0, professor_id)
    normalized = list(dict.fromkeys(requested))
    maximum = 4 if is_masterclass_course_type(course_type) else 1
    if len(normalized) > maximum:
        if maximum == 1:
            raise ValueError("Seules les activites Masterclass acceptent plusieurs professeurs")
        raise ValueError("Une Masterclass accepte au maximum 4 professeurs")
    return normalized


def replace_session_professors(
    db: Session,
    *,
    session_obj: CourseSession,
    professor_ids: list[UUID],
) -> None:
    db.execute(delete(CourseSessionProfessor).where(CourseSessionProfessor.session_id == session_obj.id))
    session_obj.professor_id = professor_ids[0] if professor_ids else None
    for position, assigned_professor_id in enumerate(professor_ids, start=1):
        db.add(
            CourseSessionProfessor(
                session_id=session_obj.id,
                professor_id=assigned_professor_id,
                position=position,
            )
        )


def assigned_professor_ids_for_session(db: Session, *, session_obj: CourseSession) -> list[UUID]:
    rows = db.scalars(
        select(CourseSessionProfessor.professor_id)
        .where(CourseSessionProfessor.session_id == session_obj.id)
        .order_by(CourseSessionProfessor.position.asc())
    ).all()
    if rows:
        return list(rows)
    return [] if session_obj.professor_id is None else [session_obj.professor_id]


def effective_professor_ids_for_session(db: Session, *, session_obj: CourseSession) -> list[UUID]:
    assigned = assigned_professor_ids_for_session(db, session_obj=session_obj)
    if session_obj.substitute_teacher_id is None:
        return assigned
    primary = session_obj.professor_id
    remaining = [professor_id for professor_id in assigned if professor_id != primary]
    return list(dict.fromkeys([session_obj.substitute_teacher_id, *remaining]))


def professor_can_manage_session(db: Session, *, session_obj: CourseSession, professor_id: UUID) -> bool:
    if effective_teacher_id_for_session(session_obj) == professor_id:
        return True
    # When the primary teacher is replaced for this occurrence, only the
    # substitute and the other Masterclass teachers retain access.
    if session_obj.professor_id == professor_id:
        return False
    return bool(
        db.scalar(
            select(
                exists(
                    select(CourseSessionProfessor.id).where(
                        CourseSessionProfessor.session_id == session_obj.id,
                        CourseSessionProfessor.professor_id == professor_id,
                        CourseSessionProfessor.position > 1,
                    )
                )
            )
        )
    )


def effective_teacher_filter_for_professor(*, professor_id: UUID) -> ColumnElement[bool]:
    return or_(
        CourseSession.substitute_teacher_id == professor_id,
        and_(
            CourseSession.substitute_teacher_id.is_(None),
            CourseSession.professor_id == professor_id,
        ),
        exists(
            select(CourseSessionProfessor.id).where(
                CourseSessionProfessor.session_id == CourseSession.id,
                CourseSessionProfessor.professor_id == professor_id,
                CourseSessionProfessor.position > 1,
            )
        ),
    )
