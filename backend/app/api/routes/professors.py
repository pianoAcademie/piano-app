from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, DeliveryMode, Location
from app.models.catalog import Professor as ProfessorModel
from app.models.catalog import SessionStatus
from app.models.ops import CommunicationSenderCategory, MessageFormat, ProfessorSessionMessage
from app.models.payout import PayoutStatus, ProfessorHourlyRate, ProfessorSessionPayout
from app.models.plan import ClientPlanSubscription, Plan, PlanKind
from app.models.professor_contract import ProfessorContractGrid, ProfessorContractGridLine, ProfessorContractGridLineRule
from app.models.professor_contract import ProfessorContractLineMode
from app.models.professor_access import ProfessorPermission
from app.models.product_catalog import CatalogProduct, ProductCategory, ProductLocationStock
from app.models.quote import Quote
from app.models.typeform_intake import TypeformIntake
from app.models.user import ClientStatus, User, UserRole
from app.schemas.booking import AttendanceUpdateRequest, BookingOut
from app.schemas.professor import (
    ProfessorAttendancePendingOut,
    ProfessorBalanceOut,
    ProfessorContractGridLineOut,
    ProfessorContractGridOut,
    ProfessorContractGridRuleOut,
    ProfessorInternalNoteListOut,
    ProfessorInternalNoteOut,
    ProfessorInternalNoteUpdateRequest,
    ProfessorLocalIntakeConfirmRequest,
    ProfessorLocalIntakeDetailOut,
    ProfessorLocalIntakePartitionOut,
    ProfessorLocalIntakeSlotOut,
    ProfessorLocalIntakeTaskOut,
    ProfessorMarkAbsenceRequest,
    ProfessorMeOut,
    ProfessorPayoutOut,
    ProfessorPermissionOut,
    ProfessorSessionCourseTypeOut,
    ProfessorSessionLocationOut,
    ProfessorSessionMessageCreateRequest,
    ProfessorSessionMessageOut,
    ProfessorSessionMessageSendOut,
    ProfessorSessionOperationOut,
    ProfessorSessionOut,
    ProfessorSessionStudentOut,
)
from app.services.professor_contracts import label_for_contract_location
from app.services.intake_local_confirmation import LOCAL_CONFIRMATION_CONFIRMED
from app.services.professor_default_grid import DefaultProfessorGridLine, load_default_professor_grid
from app.services.professor_permissions import permissions_dict
from app.services.reminders import skip_pending_reminders_for_booking
from app.services.makeup_passes import grant_makeup_for_excused_absence, revoke_pending_makeup_for_corrected_absence
from app.services.session_notifications import send_session_operation_email
from app.services.session_teachers import (
    effective_teacher_filter_for_professor,
    effective_teacher_id_for_session,
    professor_display_name,
)

router = APIRouter()

BOOKING_STATUSES_COUNTED_AS_RESERVED = (
    BookingStatus.BOOKED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _deserialize_languages(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _display_name(user: User) -> str:
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or user.email


def _resolve_professor_profile(db: Session, *, current_user: User) -> ProfessorModel:
    professor = db.scalar(select(ProfessorModel).where(ProfessorModel.email == current_user.email))
    if professor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor profile not found")
    return professor


def _resolve_professor_permissions(db: Session, *, professor_id: UUID) -> dict[str, Any]:
    row = db.scalar(select(ProfessorPermission).where(ProfessorPermission.professor_id == professor_id))
    # Legacy fallback keeps pre-existing coaches operational until explicit permission setup.
    return permissions_dict(row, legacy_if_missing=True)


def _require_professor_session(
    db: Session,
    *,
    professor_id: UUID,
    session_id: UUID,
    lock: bool = False,
) -> CourseSession:
    stmt = select(CourseSession).where(CourseSession.id == session_id)
    if lock:
        stmt = stmt.with_for_update()
    session_obj = db.scalar(stmt)
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if effective_teacher_id_for_session(session_obj) != professor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session does not belong to this professor")
    return session_obj


def _to_booking_out(booking: Booking) -> BookingOut:
    return BookingOut(
        id=booking.id,
        session_id=booking.session_id,
        client_plan_subscription_id=booking.client_plan_subscription_id,
        status=booking.status,
        booked_at=booking.booked_at,
        cancelled_at=booking.cancelled_at,
        cancellation_reason=booking.cancellation_reason,
        price_excl_vat_snapshot=booking.price_excl_vat_snapshot,
        vat_rate_snapshot=booking.vat_rate_snapshot,
        vat_amount_snapshot=booking.vat_amount_snapshot,
        total_incl_vat_snapshot=booking.total_incl_vat_snapshot,
        currency_snapshot=booking.currency_snapshot,
        waitlist_position=None,
    )


def _is_subscription_active(subscription: ClientPlanSubscription, plan: Plan, now: datetime) -> bool:
    if not plan.active:
        return False
    if subscription.status.value != "ACTIVE":
        return False
    if subscription.started_at > now:
        return False
    if subscription.ends_at is not None and subscription.ends_at <= now:
        return False
    return True


def _consume_pack_credit(subscription: ClientPlanSubscription, plan: Plan) -> bool:
    if plan.kind != PlanKind.PACK:
        return True
    if subscription.credits_remaining is None or subscription.credits_remaining <= 0:
        return False
    subscription.credits_remaining -= 1
    return True


def _restore_pack_credit(subscription: ClientPlanSubscription, plan: Plan) -> None:
    if plan.kind != PlanKind.PACK:
        return
    current = int(subscription.credits_remaining or 0)
    cap = subscription.credits_initial if subscription.credits_initial is not None else current + 1
    subscription.credits_remaining = min(current + 1, cap)


def _load_subscription_with_plan_for_update(
    db: Session,
    *,
    subscription_id: UUID,
) -> tuple[ClientPlanSubscription, Plan] | None:
    row = db.execute(
        select(ClientPlanSubscription, Plan)
        .join(Plan, Plan.id == ClientPlanSubscription.plan_id)
        .where(ClientPlanSubscription.id == subscription_id)
        .with_for_update()
    ).first()
    if row is None:
        return None
    return row[0], row[1]


def _session_students(
    db: Session,
    *,
    session_obj: CourseSession,
) -> list[ProfessorSessionStudentOut]:
    statuses = (
        BookingStatus.BOOKED,
        BookingStatus.WAITLISTED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )
    rows = db.execute(
        select(Booking, User)
        .join(User, User.id == Booking.user_id)
        .where(
            Booking.session_id == session_obj.id,
            Booking.status.in_(statuses),
        )
    ).all()

    order_map = {
        BookingStatus.BOOKED: 0,
        BookingStatus.ATTENDED: 1,
        BookingStatus.NO_SHOW: 2,
        BookingStatus.EXCUSED_ABSENCE: 3,
        BookingStatus.WAITLISTED: 4,
    }

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            order_map.get(row[0].status, 99),
            ((row[1].last_name or "") + (row[1].first_name or "") + row[1].email).lower(),
            row[0].booked_at,
        ),
    )

    out: list[ProfessorSessionStudentOut] = []
    for booking, user in sorted_rows:
        is_first_course = False
        if user.first_course_at is not None:
            delta_seconds = abs((user.first_course_at - session_obj.start_at_utc).total_seconds())
            is_first_course = delta_seconds < 60

        out.append(
            ProfessorSessionStudentOut(
                booking_id=booking.id,
                user_id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                display_name=_display_name(user),
                attendance_status=booking.status,
                is_trial_course=bool(booking.is_trial_course or user.client_status == ClientStatus.TRIAL),
                is_first_course=is_first_course,
                internal_note=booking.internal_note,
            )
        )
    return out


def _serialize_professor_contract_grid(db: Session, *, grid: ProfessorContractGrid) -> ProfessorContractGridOut:
    lines = db.scalars(
        select(ProfessorContractGridLine)
        .where(ProfessorContractGridLine.grid_id == grid.id)
        .order_by(ProfessorContractGridLine.display_order.asc(), ProfessorContractGridLine.created_at.asc())
    ).all()

    line_ids = [line.id for line in lines]
    course_type_ids = sorted({line.course_type_id for line in lines if line.course_type_id is not None})
    course_type_rows = (
        db.scalars(select(CourseType).where(CourseType.id.in_(course_type_ids))).all()
        if course_type_ids
        else []
    )
    course_type_name_by_id = {row.id: row.name for row in course_type_rows}
    rules_rows = (
        db.scalars(
            select(ProfessorContractGridLineRule)
            .where(ProfessorContractGridLineRule.line_id.in_(line_ids))
            .order_by(
                ProfessorContractGridLineRule.line_id.asc(),
                ProfessorContractGridLineRule.display_order.asc(),
                ProfessorContractGridLineRule.min_students.asc(),
                ProfessorContractGridLineRule.created_at.asc(),
            )
        ).all()
        if line_ids
        else []
    )
    rules_by_line: dict[UUID, list[ProfessorContractGridRuleOut]] = {line_id: [] for line_id in line_ids}
    for rule in rules_rows:
        rules_by_line.setdefault(rule.line_id, []).append(
            ProfessorContractGridRuleOut(
                min_students=rule.min_students,
                max_students=rule.max_students,
                hourly_rate=rule.hourly_rate,
            )
        )

    return ProfessorContractGridOut(
        grid_id=grid.id,
        valid_from=grid.valid_from,
        valid_to=grid.valid_to,
        location_code=grid.location_code,
        location_label=label_for_contract_location(grid.location_code),
        notes=grid.notes,
        lines=[
            ProfessorContractGridLineOut(
                course_type_id=line.course_type_id,
                course_type_name=course_type_name_by_id.get(line.course_type_id, line.service_type),
                service_type=line.service_type,
                mode=line.mode,
                reference_duration_minutes=line.reference_duration_minutes,
                default_hourly_rate=line.default_hourly_rate,
                rules=rules_by_line.get(line.id, []),
            )
            for line in lines
        ],
    )


def _school_year_bounds_for_day(reference_date: date) -> tuple[datetime, datetime]:
    start_year = reference_date.year if reference_date.month >= 8 else reference_date.year - 1
    return (
        datetime(start_year, 8, 1, tzinfo=timezone.utc),
        datetime(start_year + 1, 8, 1, tzinfo=timezone.utc),
    )


def _planned_professor_course_type_ids(
    db: Session,
    *,
    professor_id: UUID,
    reference_date: date,
) -> set[UUID]:
    season_start, season_end = _school_year_bounds_for_day(reference_date)
    rows = db.scalars(
        select(CourseSession.course_type_id)
        .where(
            effective_teacher_filter_for_professor(professor_id=professor_id),
            CourseSession.start_at_utc >= season_start,
            CourseSession.start_at_utc < season_end,
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .distinct()
    ).all()
    return set(rows)


def _filter_contract_grid_to_course_types(
    grid: ProfessorContractGridOut,
    *,
    course_type_ids: set[UUID],
) -> ProfessorContractGridOut:
    return grid.model_copy(
        update={
            "lines": [
                line
                for line in grid.lines
                if line.course_type_id is not None and line.course_type_id in course_type_ids
            ]
        }
    )


def _serialize_professor_rate_rules(raw_rules: object) -> list[ProfessorContractGridRuleOut]:
    if not isinstance(raw_rules, list):
        return []

    out: list[ProfessorContractGridRuleOut] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        try:
            min_students = int(raw_rule.get("min_students"))
        except (TypeError, ValueError):
            continue
        if min_students < 0:
            continue

        max_students_raw = raw_rule.get("max_students")
        if max_students_raw is None:
            max_students: int | None = None
        else:
            try:
                max_students = int(max_students_raw)
            except (TypeError, ValueError):
                continue
            if max_students < min_students:
                continue

        try:
            hourly_rate = Decimal(str(raw_rule.get("hourly_rate")))
        except Exception:
            continue
        if hourly_rate < 0:
            continue

        out.append(
            ProfessorContractGridRuleOut(
                min_students=min_students,
                max_students=max_students,
                hourly_rate=hourly_rate,
            )
        )

    out.sort(key=lambda row: (row.min_students, row.max_students if row.max_students is not None else 10**9))
    return out


def _default_grid_rules_to_contract_rules(line: DefaultProfessorGridLine) -> list[ProfessorContractGridRuleOut]:
    return [
        ProfessorContractGridRuleOut(
            min_students=rule.min_students,
            max_students=rule.max_students,
            hourly_rate=Decimal(rule.hourly_rate),
        )
        for rule in line.rules
    ]


def _contract_mode_from_course_type(course_type: CourseType) -> ProfessorContractLineMode:
    if course_type.mode == DeliveryMode.ONLINE:
        return ProfessorContractLineMode.EN_LIGNE
    if course_type.mode == DeliveryMode.ONSITE:
        return ProfessorContractLineMode.PRESENTIEL
    return ProfessorContractLineMode.AUTRE


def _build_effective_contract_grid(
    db: Session,
    *,
    professor_id: UUID,
    reference_date: date,
) -> ProfessorContractGridOut | None:
    active_rates = db.scalars(
        select(ProfessorHourlyRate)
        .where(
            ProfessorHourlyRate.professor_id == professor_id,
            ProfessorHourlyRate.location_id.is_(None),
            ProfessorHourlyRate.valid_from <= reference_date,
            or_(ProfessorHourlyRate.valid_to.is_(None), ProfessorHourlyRate.valid_to >= reference_date),
        )
        .order_by(ProfessorHourlyRate.valid_from.desc(), ProfessorHourlyRate.created_at.desc())
    ).all()

    active_global_rate: ProfessorHourlyRate | None = None
    active_rates_by_course_type: dict[UUID, ProfessorHourlyRate] = {}
    for row in active_rates:
        if row.course_type_id is None:
            if active_global_rate is None:
                active_global_rate = row
            continue
        if row.course_type_id not in active_rates_by_course_type:
            active_rates_by_course_type[row.course_type_id] = row

    default_grid_lines, _ = load_default_professor_grid(db)
    default_grid_by_course_type = {line.course_type_id: line for line in default_grid_lines}
    session_course_type_ids = db.scalars(
        select(CourseSession.course_type_id)
        .where(
            CourseSession.professor_id == professor_id,
            CourseSession.course_type_id.is_not(None),
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .distinct()
    ).all()

    course_type_ids = sorted(
        {
            *default_grid_by_course_type.keys(),
            *active_rates_by_course_type.keys(),
            *session_course_type_ids,
        },
        key=str,
    )
    course_types = (
        db.scalars(select(CourseType).where(CourseType.id.in_(course_type_ids)).order_by(CourseType.name.asc())).all()
        if course_type_ids
        else []
    )

    lines: list[ProfessorContractGridLineOut] = []

    for course_type in course_types:
        rate_row = active_rates_by_course_type.get(course_type.id)
        default_line = default_grid_by_course_type.get(course_type.id)

        rules = _serialize_professor_rate_rules(rate_row.headcount_rules_json) if rate_row is not None else []
        if not rules and default_line is not None:
            rules = _default_grid_rules_to_contract_rules(default_line)

        default_hourly_rate: Decimal | None = None
        if rate_row is not None and rate_row.hourly_rate is not None:
            default_hourly_rate = Decimal(rate_row.hourly_rate)
        elif default_line is not None and default_line.default_hourly_rate is not None:
            default_hourly_rate = Decimal(default_line.default_hourly_rate)
        elif active_global_rate is not None and active_global_rate.hourly_rate is not None:
            default_hourly_rate = Decimal(active_global_rate.hourly_rate)
        elif course_type.default_hourly_rate is not None:
            default_hourly_rate = Decimal(course_type.default_hourly_rate)

        if default_hourly_rate is None and not rules:
            continue

        lines.append(
            ProfessorContractGridLineOut(
                course_type_id=course_type.id,
                course_type_name=course_type.name,
                service_type=course_type.name,
                mode=_contract_mode_from_course_type(course_type),
                reference_duration_minutes=course_type.duration_minutes,
                default_hourly_rate=default_hourly_rate,
                rules=rules,
            )
        )

    if not lines:
        return None

    valid_from_candidates = [row.valid_from for row in active_rates_by_course_type.values()]
    if active_global_rate is not None:
        valid_from_candidates.append(active_global_rate.valid_from)

    return ProfessorContractGridOut(
        grid_id=uuid5(NAMESPACE_URL, f"professor-effective-grid:{professor_id}:{reference_date.isoformat()}"),
        valid_from=min(valid_from_candidates) if valid_from_candidates else reference_date,
        valid_to=None,
        location_code=None,
        location_label="Configuration effective",
        notes="Grille effective (generale + surcouche activite professeur)",
        lines=lines,
    )


@router.get("/professors/me", response_model=ProfessorMeOut)
def get_my_professor_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> ProfessorMeOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)

    return ProfessorMeOut(
        id=professor.id,
        email=professor.email,
        first_name=professor.first_name,
        last_name=professor.last_name,
        phone=professor.phone,
        zoom_link=professor.zoom_link,
        spoken_languages=_deserialize_languages(professor.spoken_languages),
        is_coach=professor.is_coach,
        active=professor.active,
        payout_currency=professor.payout_currency,
        daily_schedule_email_enabled=professor.daily_schedule_email_enabled,
        daily_schedule_email_time=professor.daily_schedule_email_time,
        daily_schedule_skip_if_no_course=professor.daily_schedule_skip_if_no_course,
        permissions=ProfessorPermissionOut(**permissions),
    )


@router.get("/professors/me/sessions", response_model=list[ProfessorSessionOut])
def list_my_professor_sessions(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    include_students: bool = False,
    scope: str = Query(default="mine", pattern="^(mine|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorSessionOut]:
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be before 'to'",
        )

    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)
    if not permissions["can_view_planning"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Planning access denied")
    can_view_all_school_sessions = bool(
        permissions.get("can_view_all_school_sessions", False)
        or permissions.get("can_view_other_teachers_sessions", False)
        or permissions.get("can_manage_other_teachers_students_and_sessions", False)
    )
    show_all_school_sessions = scope == "all" and can_view_all_school_sessions

    booked_counts = (
        select(
            Booking.session_id.label("session_id"),
            func.count(Booking.id).label("booked_count"),
        )
        .where(Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED))
        .group_by(Booking.session_id)
        .subquery()
    )

    stmt = (
        select(
            CourseSession,
            CourseType,
            Location,
            func.coalesce(booked_counts.c.booked_count, 0).label("booked_count"),
        )
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(booked_counts, booked_counts.c.session_id == CourseSession.id)
    )

    if not show_all_school_sessions:
        stmt = stmt.where(effective_teacher_filter_for_professor(professor_id=professor.id))

    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)

    rows = db.execute(stmt.order_by(CourseSession.start_at_utc.asc())).all()
    sessions = [row[0] for row in rows]

    teacher_ids = {
        teacher_id
        for session_obj in sessions
        for teacher_id in (session_obj.professor_id, session_obj.substitute_teacher_id)
        if teacher_id is not None
    }
    professors_by_id = (
        {
            professor_obj.id: professor_obj
            for professor_obj in db.scalars(select(ProfessorModel).where(ProfessorModel.id.in_(teacher_ids))).all()
        }
        if teacher_ids
        else {}
    )

    students_by_session: dict[UUID, list[ProfessorSessionStudentOut]] = {}
    if include_students and sessions:
        for session_obj in sessions:
            # With school-wide visibility, keep student roster visibility restricted
            # to the collaborator's own sessions unless explicit client rights are granted.
            if (
                show_all_school_sessions
                and effective_teacher_id_for_session(session_obj) != professor.id
                and not permissions["can_view_clients"]
            ):
                students_by_session[session_obj.id] = []
            else:
                students_by_session[session_obj.id] = _session_students(db, session_obj=session_obj)

    return [
        ProfessorSessionOut(
            id=session.id,
            title=session.title,
            description=session.description,
            internal_note=session.internal_note,
            start_at_utc=session.start_at_utc,
            end_at_utc=session.end_at_utc,
            status=session.status,
            capacity_max=session.capacity_max,
            booked_count=int(booked_count or 0),
            zoom_link=session.zoom_link,
            habitual_teacher_id=session.professor_id,
            habitual_teacher_display_name=professor_display_name(professors_by_id.get(session.professor_id)),
            substitute_teacher_id=session.substitute_teacher_id,
            substitute_teacher_display_name=(
                professor_display_name(professors_by_id.get(session.substitute_teacher_id))
                if session.substitute_teacher_id is not None
                else None
            ),
            effective_teacher_id=effective_teacher_id_for_session(session),
            effective_teacher_display_name=professor_display_name(
                professors_by_id.get(effective_teacher_id_for_session(session))
            ),
            students=students_by_session.get(session.id, []),
            course_type=ProfessorSessionCourseTypeOut(
                id=course_type.id,
                code=course_type.code,
                name=course_type.name,
            ),
            location=ProfessorSessionLocationOut(
                id=location.id,
                code=location.code,
                name=location.name,
                is_online=location.is_online,
            ),
        )
        for session, course_type, location, booked_count in rows
    ]


_FRENCH_WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_FRENCH_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def _normalized_intake_payload(intake: TypeformIntake) -> dict[str, object]:
    return intake.normalized_payload_json if isinstance(intake.normalized_payload_json, dict) else {}


def _intake_people(intake: TypeformIntake) -> tuple[str, str | None]:
    normalized = _normalized_intake_payload(intake)
    parent = " ".join(
        str(normalized.get(key) or "").strip()
        for key in ("parent_first_name", "parent_last_name")
        if str(normalized.get(key) or "").strip()
    )
    child = " ".join(
        str(normalized.get(key) or "").strip()
        for key in ("child_first_name", "child_last_name")
        if str(normalized.get(key) or "").strip()
    )
    email = str(normalized.get("parent_email") or "").strip()
    return parent or email or "Prospect", child or None


def _intake_requested_summary(intake: TypeformIntake) -> str | None:
    normalized = _normalized_intake_payload(intake)
    values: list[str] = []
    for key in (
        "requested_activity",
        "requested_course",
        "requested_formula",
        "requested_formula_type",
        "instrument",
    ):
        value = normalized.get(key)
        for item in value if isinstance(value, list) else [value]:
            text = str(item or "").strip()
            if text and text.lower() not in {existing.lower() for existing in values}:
                values.append(text)
    return " · ".join(values) or None


def _local_intake_task_out(intake: TypeformIntake) -> ProfessorLocalIntakeTaskOut:
    prospect_label, child_label = _intake_people(intake)
    return ProfessorLocalIntakeTaskOut(
        id=intake.id,
        received_at=intake.received_at,
        local_confirmation_status=intake.local_confirmation_status,
        prospect_label=prospect_label,
        child_label=child_label,
        requested_summary=_intake_requested_summary(intake),
        detected_location=intake.detected_location,
        local_confirmation_schedule_snapshot=intake.local_confirmation_schedule_snapshot,
        local_confirmation_partition_snapshot=intake.local_confirmation_partition_snapshot,
        local_confirmation_confirmed_at=intake.local_confirmation_confirmed_at,
    )


def _local_intake_quote_still_actionable():
    return or_(
        TypeformIntake.related_quote_id.is_(None),
        and_(
            Quote.sent_at.is_(None),
            Quote.approved_at.is_(None),
            Quote.rejected_at.is_(None),
            func.lower(Quote.status).notin_(("sent", "approved", "rejected", "cancelled", "expired")),
        ),
    )


def _require_assigned_local_intake(
    db: Session,
    *,
    intake_id: UUID,
    professor_id: UUID,
    lock: bool = False,
) -> TypeformIntake:
    stmt = (
        select(TypeformIntake)
        .outerjoin(Quote, Quote.id == TypeformIntake.related_quote_id)
        .where(
            TypeformIntake.id == intake_id,
            TypeformIntake.local_confirmation_assignee_professor_id == professor_id,
            _local_intake_quote_still_actionable(),
        )
    )
    if lock:
        stmt = stmt.with_for_update()
    intake = db.scalar(stmt)
    if intake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local intake confirmation not found")
    return intake


def _local_intake_slot_options(db: Session, *, professor_id: UUID) -> list[ProfessorLocalIntakeSlotOut]:
    booked_counts = (
        select(Booking.session_id.label("session_id"), func.count(Booking.id).label("booked_count"))
        .where(Booking.status.in_(BOOKING_STATUSES_COUNTED_AS_RESERVED))
        .group_by(Booking.session_id)
        .subquery()
    )
    rows = db.execute(
        select(
            CourseSession,
            CourseType,
            Location,
            func.coalesce(booked_counts.c.booked_count, 0).label("booked_count"),
        )
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(booked_counts, booked_counts.c.session_id == CourseSession.id)
        .where(
            effective_teacher_filter_for_professor(professor_id=professor_id),
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= _utcnow(),
            or_(Location.code.ilike("%bar%duc%"), Location.name.ilike("%bar%duc%")),
        )
        .order_by(CourseSession.start_at_utc.asc())
        .limit(400)
    ).all()

    options: list[ProfessorLocalIntakeSlotOut] = []
    seen: set[object] = set()
    for session_obj, course_type, location, booked_count in rows:
        dedupe_key: object = session_obj.recurrence_group_id or session_obj.id
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        try:
            local_start = session_obj.start_at_utc.astimezone(ZoneInfo(session_obj.timezone or location.timezone))
        except Exception:
            local_start = session_obj.start_at_utc.astimezone(timezone.utc)
        label = (
            f"{_FRENCH_WEEKDAYS[local_start.weekday()].capitalize()} à {local_start:%H:%M}"
            f" · {course_type.name} · prochain le {local_start.day} {_FRENCH_MONTHS[local_start.month - 1]}"
        )
        reserved = int(booked_count or 0)
        options.append(
            ProfessorLocalIntakeSlotOut(
                session_id=session_obj.id,
                label=label,
                start_at_utc=session_obj.start_at_utc,
                end_at_utc=session_obj.end_at_utc,
                timezone=session_obj.timezone or location.timezone,
                course_type_name=course_type.name,
                location_name=location.name,
                capacity_max=session_obj.capacity_max,
                booked_count=reserved,
                seats_remaining=max(session_obj.capacity_max - reserved, 0),
                recurrence_group_id=session_obj.recurrence_group_id,
            )
        )
    return options


def _local_intake_partition_options(db: Session) -> list[ProfessorLocalIntakePartitionOut]:
    bld_location_ids = list(
        db.scalars(
            select(Location.id).where(
                or_(Location.code.ilike("%bar%duc%"), Location.name.ilike("%bar%duc%"))
            )
        ).all()
    )
    stock_join = and_(ProductLocationStock.product_id == CatalogProduct.id)
    if bld_location_ids:
        stock_join = and_(stock_join, ProductLocationStock.location_id.in_(bld_location_ids))
    rows = db.execute(
        select(
            CatalogProduct,
            ProductCategory,
            func.coalesce(func.sum(ProductLocationStock.real_quantity), 0).label("real_quantity"),
            func.coalesce(func.sum(ProductLocationStock.estimated_quantity), 0).label("estimated_quantity"),
        )
        .outerjoin(ProductCategory, ProductCategory.id == CatalogProduct.category_id)
        .outerjoin(ProductLocationStock, stock_join)
        .where(
            CatalogProduct.active.is_(True),
            or_(
                ProductCategory.code.ilike("%partition%"),
                ProductCategory.name.ilike("%partition%"),
                CatalogProduct.title.ilike("%partition%"),
            ),
        )
        .group_by(CatalogProduct.id, ProductCategory.id)
        .order_by(CatalogProduct.title.asc())
        .limit(500)
    ).all()
    return [
        ProfessorLocalIntakePartitionOut(
            product_id=product.id,
            title=product.title,
            category_name=category.name if category is not None else None,
            real_quantity=int(real_quantity or 0),
            estimated_quantity=int(estimated_quantity or 0),
        )
        for product, category, real_quantity, estimated_quantity in rows
    ]


def _local_intake_detail_out(
    db: Session,
    *,
    intake: TypeformIntake,
    professor_id: UUID,
) -> ProfessorLocalIntakeDetailOut:
    task = _local_intake_task_out(intake)
    return ProfessorLocalIntakeDetailOut(
        **task.model_dump(),
        normalized_payload_json=_normalized_intake_payload(intake),
        slot_options=_local_intake_slot_options(db, professor_id=professor_id),
        partition_options=_local_intake_partition_options(db),
        local_confirmation_session_id=intake.local_confirmation_session_id,
        local_confirmation_product_id=intake.local_confirmation_product_id,
        local_confirmation_partition_not_required=intake.local_confirmation_partition_not_required,
        local_confirmation_comment=intake.local_confirmation_comment,
    )


@router.get("/professors/me/intakes/local-confirmations", response_model=list[ProfessorLocalIntakeTaskOut])
def list_my_local_intake_confirmations(
    status_filter: str = Query(default="PENDING", alias="status", pattern="^(PENDING|CONFIRMED|ALL)$"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorLocalIntakeTaskOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    stmt = (
        select(TypeformIntake)
        .outerjoin(Quote, Quote.id == TypeformIntake.related_quote_id)
        .where(
            TypeformIntake.local_confirmation_assignee_professor_id == professor.id,
            _local_intake_quote_still_actionable(),
        )
    )
    if status_filter != "ALL":
        stmt = stmt.where(TypeformIntake.local_confirmation_status == status_filter)
    intakes = db.scalars(
        stmt.order_by(TypeformIntake.received_at.desc()).limit(limit)
    ).all()
    return [_local_intake_task_out(intake) for intake in intakes]


@router.get(
    "/professors/me/intakes/local-confirmations/{intake_id}",
    response_model=ProfessorLocalIntakeDetailOut,
)
def get_my_local_intake_confirmation(
    intake_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> ProfessorLocalIntakeDetailOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    intake = _require_assigned_local_intake(db, intake_id=intake_id, professor_id=professor.id)
    return _local_intake_detail_out(db, intake=intake, professor_id=professor.id)


@router.patch(
    "/professors/me/intakes/local-confirmations/{intake_id}",
    response_model=ProfessorLocalIntakeDetailOut,
)
def confirm_my_local_intake(
    intake_id: UUID,
    payload: ProfessorLocalIntakeConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> ProfessorLocalIntakeDetailOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    intake = _require_assigned_local_intake(
        db, intake_id=intake_id, professor_id=professor.id, lock=True
    )
    slots = {option.session_id: option for option in _local_intake_slot_options(db, professor_id=professor.id)}
    selected_slot = slots.get(payload.session_id)
    if selected_slot is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le créneau choisi n'est plus disponible dans votre planning Bar-le-Duc.",
        )

    custom_partition = (payload.custom_partition or "").strip()
    selection_count = int(payload.product_id is not None) + int(bool(custom_partition)) + int(payload.partition_not_required)
    if selection_count != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choisissez une partition, saisissez une partition libre ou indiquez qu'aucune partition n'est nécessaire.",
        )

    partition_snapshot: str
    selected_product_id: UUID | None = None
    if payload.product_id is not None:
        products = {option.product_id: option for option in _local_intake_partition_options(db)}
        selected_product = products.get(payload.product_id)
        if selected_product is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Partition introuvable dans le catalogue.")
        selected_product_id = selected_product.product_id
        partition_snapshot = selected_product.title
    elif custom_partition:
        partition_snapshot = custom_partition
    else:
        partition_snapshot = "Aucune partition nécessaire"

    intake.local_confirmation_session_id = selected_slot.session_id
    intake.local_confirmation_product_id = selected_product_id
    intake.local_confirmation_schedule_snapshot = selected_slot.label
    intake.local_confirmation_partition_snapshot = partition_snapshot
    intake.local_confirmation_partition_not_required = payload.partition_not_required
    intake.local_confirmation_comment = (payload.comment or "").strip() or None
    intake.local_confirmation_status = LOCAL_CONFIRMATION_CONFIRMED
    intake.local_confirmation_confirmed_at = _utcnow()
    intake.local_confirmation_confirmed_by_user_id = current_user.id
    intake.local_confirmation_confirmed_by_name = _display_name(current_user)
    intake.updated_at = _utcnow()
    db.add(intake)
    db.commit()
    db.refresh(intake)
    return _local_intake_detail_out(db, intake=intake, professor_id=professor.id)


def _require_internal_note_permission(permissions: dict[str, Any]) -> None:
    if not (
        permissions.get("can_take_attendance")
        or permissions.get("can_edit_own_sessions")
        or permissions.get("can_edit_planning")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal note permission denied")


def _normalize_internal_note(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


@router.get("/professors/me/notes", response_model=list[ProfessorInternalNoteListOut])
def list_my_internal_notes(
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorInternalNoteListOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)
    if not permissions["can_view_planning"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Planning access denied")

    session_note_rows = db.execute(
        select(CourseSession, CourseType, Location)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            effective_teacher_filter_for_professor(professor_id=professor.id),
            CourseSession.internal_note.is_not(None),
            func.length(func.trim(CourseSession.internal_note)) > 0,
        )
    ).all()
    student_note_rows = db.execute(
        select(Booking, CourseSession, CourseType, Location, User)
        .join(CourseSession, CourseSession.id == Booking.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(User, User.id == Booking.user_id)
        .where(
            effective_teacher_filter_for_professor(professor_id=professor.id),
            Booking.internal_note.is_not(None),
            func.length(func.trim(Booking.internal_note)) > 0,
        )
    ).all()

    notes = [
        ProfessorInternalNoteListOut(
            id=f"SESSION:{session_obj.id}",
            note_type="SESSION",
            body=session_obj.internal_note or "",
            session_id=session_obj.id,
            session_title=session_obj.title,
            session_start_at_utc=session_obj.start_at_utc,
            session_timezone=session_obj.timezone,
            course_type_name=course_type.name,
            location_id=location.id,
            location_name=location.name,
        )
        for session_obj, course_type, location in session_note_rows
    ]
    notes.extend(
        ProfessorInternalNoteListOut(
            id=f"STUDENT:{booking.id}",
            note_type="STUDENT",
            body=booking.internal_note or "",
            session_id=session_obj.id,
            booking_id=booking.id,
            student_id=student.id,
            student_display_name=_display_name(student),
            session_title=session_obj.title,
            session_start_at_utc=session_obj.start_at_utc,
            session_timezone=session_obj.timezone,
            course_type_name=course_type.name,
            location_id=location.id,
            location_name=location.name,
        )
        for booking, session_obj, course_type, location, student in student_note_rows
    )
    notes.sort(key=lambda note: note.session_start_at_utc, reverse=True)
    return notes[:limit]


@router.patch("/professors/me/sessions/{session_id}/internal-note", response_model=ProfessorInternalNoteOut)
def update_my_session_internal_note(
    session_id: UUID,
    payload: ProfessorInternalNoteUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> ProfessorInternalNoteOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)
    _require_internal_note_permission(permissions)
    session_obj = _require_professor_session(
        db,
        professor_id=professor.id,
        session_id=session_id,
        lock=True,
    )
    session_obj.internal_note = _normalize_internal_note(payload.internal_note)
    session_obj.updated_at = _utcnow()
    db.commit()
    db.refresh(session_obj)
    return ProfessorInternalNoteOut(session_id=session_obj.id, internal_note=session_obj.internal_note)


@router.patch(
    "/professors/me/sessions/{session_id}/bookings/{booking_id}/internal-note",
    response_model=ProfessorInternalNoteOut,
)
def update_my_booking_internal_note(
    session_id: UUID,
    booking_id: UUID,
    payload: ProfessorInternalNoteUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> ProfessorInternalNoteOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)
    _require_internal_note_permission(permissions)
    session_obj = _require_professor_session(
        db,
        professor_id=professor.id,
        session_id=session_id,
        lock=True,
    )
    booking = db.scalar(
        select(Booking)
        .where(
            Booking.id == booking_id,
            Booking.session_id == session_obj.id,
            Booking.status.in_((
                BookingStatus.BOOKED,
                BookingStatus.ATTENDED,
                BookingStatus.NO_SHOW,
                BookingStatus.EXCUSED_ABSENCE,
            )),
        )
        .with_for_update()
    )
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    booking.internal_note = _normalize_internal_note(payload.internal_note)
    db.commit()
    db.refresh(booking)
    return ProfessorInternalNoteOut(
        session_id=session_obj.id,
        booking_id=booking.id,
        internal_note=booking.internal_note,
    )


@router.get("/professors/me/sessions/{session_id}/bookings", response_model=list[ProfessorSessionStudentOut])
def list_my_session_students(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorSessionStudentOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)
    if not permissions["can_view_planning"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Planning access denied")

    session_obj = _require_professor_session(db, professor_id=professor.id, session_id=session_id)
    return _session_students(db, session_obj=session_obj)


@router.get("/professors/me/attendance/pending", response_model=list[ProfessorAttendancePendingOut])
def list_pending_attendance(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorAttendancePendingOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)
    if not permissions["can_view_planning"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Planning access denied")

    now = _utcnow()
    tracked_statuses = (
        BookingStatus.BOOKED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )
    pending_count_expr = func.sum(case((Booking.status == BookingStatus.BOOKED, 1), else_=0))
    total_count_expr = func.sum(case((Booking.status.in_(tracked_statuses), 1), else_=0))

    rows = db.execute(
        select(
            CourseSession,
            CourseType,
            Location,
            func.coalesce(pending_count_expr, 0).label("pending_count"),
            func.coalesce(total_count_expr, 0).label("total_count"),
        )
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(
            Booking,
            (Booking.session_id == CourseSession.id) & (Booking.status.in_(tracked_statuses)),
        )
        .where(
            CourseSession.professor_id == professor.id,
            CourseSession.end_at_utc <= now,
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .group_by(CourseSession.id, CourseType.id, Location.id)
        .having(func.coalesce(pending_count_expr, 0) > 0)
        .order_by(CourseSession.end_at_utc.desc())
        .limit(limit)
    ).all()

    return [
        ProfessorAttendancePendingOut(
            session_id=session_obj.id,
            title=session_obj.title,
            start_at_utc=session_obj.start_at_utc,
            end_at_utc=session_obj.end_at_utc,
            location_name=location.name,
            course_type_name=course_type.name,
            pending_students_count=int(pending_count or 0),
            total_students_count=int(total_count or 0),
        )
        for session_obj, course_type, location, pending_count, total_count in rows
    ]


@router.get("/professors/me/payouts", response_model=list[ProfessorPayoutOut])
def list_my_payouts(
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorPayoutOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)

    rows = db.execute(
        select(ProfessorSessionPayout, CourseSession, CourseType, Location)
        .join(CourseSession, CourseSession.id == ProfessorSessionPayout.session_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(ProfessorSessionPayout.professor_id == professor.id)
        .order_by(CourseSession.start_at_utc.desc())
        .limit(limit)
    ).all()

    return [
        ProfessorPayoutOut(
            payout_id=payout.id,
            session_id=session_obj.id,
            session_title=session_obj.title,
            session_start_at_utc=session_obj.start_at_utc,
            session_end_at_utc=session_obj.end_at_utc,
            location_name=location.name,
            course_type_name=course_type.name,
            duration_hours=payout.duration_hours,
            amount_snapshot=payout.amount_snapshot,
            currency_snapshot=payout.currency_snapshot,
            payout_status=payout.payout_status,
            paid_at=payout.paid_at,
        )
        for payout, session_obj, course_type, location in rows
    ]


@router.get("/professors/me/balance", response_model=ProfessorBalanceOut)
def get_my_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> ProfessorBalanceOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    currency = (professor.payout_currency or "EUR").strip().upper() or "EUR"

    rows = db.execute(
        select(ProfessorSessionPayout)
        .where(
            ProfessorSessionPayout.professor_id == professor.id,
            ProfessorSessionPayout.currency_snapshot == currency,
        )
    ).scalars().all()

    pending_amount = Decimal("0.00")
    approved_amount = Decimal("0.00")
    paid_amount = Decimal("0.00")
    pending_sessions = 0
    approved_sessions = 0
    paid_sessions = 0

    for payout in rows:
        amount = Decimal(payout.amount_snapshot or 0)
        if payout.payout_status == PayoutStatus.PENDING:
            pending_amount += amount
            pending_sessions += 1
        elif payout.payout_status == PayoutStatus.APPROVED:
            approved_amount += amount
            approved_sessions += 1
        elif payout.payout_status == PayoutStatus.PAID:
            paid_amount += amount
            paid_sessions += 1

    return ProfessorBalanceOut(
        currency=currency,
        pending_amount=pending_amount,
        approved_amount=approved_amount,
        paid_amount=paid_amount,
        total_amount=pending_amount + approved_amount + paid_amount,
        pending_sessions=pending_sessions,
        approved_sessions=approved_sessions,
        paid_sessions=paid_sessions,
    )


@router.get("/professors/me/contract-grids", response_model=list[ProfessorContractGridOut])
def list_my_contract_grids(
    on_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorContractGridOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    reference_date = on_date or date.today()
    planned_course_type_ids = _planned_professor_course_type_ids(
        db,
        professor_id=professor.id,
        reference_date=reference_date,
    )
    if not planned_course_type_ids:
        return []

    effective_grid = _build_effective_contract_grid(
        db,
        professor_id=professor.id,
        reference_date=reference_date,
    )
    if effective_grid is not None:
        visible_grid = _filter_contract_grid_to_course_types(
            effective_grid,
            course_type_ids=planned_course_type_ids,
        )
        return [visible_grid] if visible_grid.lines else []

    grids = db.scalars(
        select(ProfessorContractGrid)
        .where(
            ProfessorContractGrid.professor_id == professor.id,
            ProfessorContractGrid.valid_from <= reference_date,
            or_(ProfessorContractGrid.valid_to.is_(None), ProfessorContractGrid.valid_to >= reference_date),
        )
        .order_by(ProfessorContractGrid.valid_from.desc(), ProfessorContractGrid.created_at.desc())
    ).all()
    visible_grids = [
        _filter_contract_grid_to_course_types(
            _serialize_professor_contract_grid(db, grid=grid),
            course_type_ids=planned_course_type_ids,
        )
        for grid in grids
    ]
    return [grid for grid in visible_grids if grid.lines]


@router.get("/professors/me/messages", response_model=list[ProfessorSessionMessageOut])
def list_my_session_messages(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> list[ProfessorSessionMessageOut]:
    professor = _resolve_professor_profile(db, current_user=current_user)
    rows = db.scalars(
        select(ProfessorSessionMessage)
        .where(ProfessorSessionMessage.professor_id == professor.id)
        .order_by(ProfessorSessionMessage.sent_at.desc())
        .limit(limit)
    ).all()

    return [
        ProfessorSessionMessageOut(
            id=row.id,
            session_id=row.session_id,
            subject=row.subject,
            body=row.body,
            body_format=row.body_format,
            recipient_count=row.recipient_count,
            sent_at=row.sent_at,
        )
        for row in rows
    ]


@router.post("/professors/me/sessions/{session_id}/messages", response_model=ProfessorSessionMessageSendOut)
def send_session_message(
    session_id: UUID,
    payload: ProfessorSessionMessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> ProfessorSessionMessageSendOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)
    if not permissions["can_message_clients"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Messaging permission denied")

    session_obj = _require_professor_session(db, professor_id=professor.id, session_id=session_id)
    subject = payload.subject.strip()
    body = payload.body.strip()
    if not subject or not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Subject and body are required")

    booking_statuses = (
        BookingStatus.BOOKED,
        BookingStatus.WAITLISTED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    )
    requested_scope = (payload.recipient_scope or "GROUP").strip().upper()
    is_admin_only = requested_scope in {"ADMIN", "ADMINISTRATION", "STAFF"} and payload.target_user_id is None
    is_individual = requested_scope in {"STUDENT", "INDIVIDUAL", "INDIVIDUAL_STUDENT"} or payload.target_user_id is not None

    recipients: list[tuple[str, UUID | None]] = []
    target_display_name: str | None = None
    if is_admin_only:
        admin_rows = db.scalars(
            select(User)
            .where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.email.is_not(None),
            )
            .order_by(User.created_at.asc())
        ).all()
        recipients = sorted(
            {
                ((row.email or "").strip().lower(), row.id)
                for row in admin_rows
                if row.email and row.email.strip()
            },
            key=lambda item: item[0],
        )
        target_display_name = "Administration"
    elif is_individual:
        if payload.target_user_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Target student is required")

        target = db.execute(
            select(User)
            .join(Booking, Booking.user_id == User.id)
            .where(
                Booking.session_id == session_id,
                Booking.user_id == payload.target_user_id,
                Booking.status.in_(booking_statuses),
                User.email_opt_in.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
        if target is None or not target.email or not target.email.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Target student not found or no email opt-in",
            )
        recipients = [(target.email.strip().lower(), target.id)]
        target_display_name = _display_name(target)
    else:
        recipient_rows = db.execute(
            select(User.id, User.email)
            .join(Booking, Booking.user_id == User.id)
            .where(
                Booking.session_id == session_id,
                Booking.status.in_(booking_statuses),
                User.email_opt_in.is_(True),
            )
        ).all()
        recipients = sorted(
            {
                (((email or "").strip().lower()), user_id)
                for user_id, email in recipient_rows
                if email and email.strip()
            },
            key=lambda item: item[0],
        )

    if not recipients:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No valid recipient found")

    operation = "PROF_ADMIN_NOTE" if is_admin_only else "PROF_GROUP_MESSAGE"
    for email, recipient_user_id in recipients:
        send_session_operation_email(
            to_email=email,
            subject=subject,
            body=body,
            body_format=payload.body_format.value,
            operation=operation,
            session_title=session_obj.title,
            sender_user_id=current_user.id,
            sender_label=_display_name(current_user),
            sender_category=CommunicationSenderCategory.PROFESSOR,
            professor_id=professor.id,
            recipient_user_id=recipient_user_id,
        )

    now = _utcnow()
    if target_display_name is None:
        logged_subject = subject
    elif target_display_name == "Administration":
        logged_subject = f"{subject} (administration)"
    else:
        logged_subject = f"{subject} (eleve: {target_display_name})"
    message_log = ProfessorSessionMessage(
        session_id=session_obj.id,
        professor_id=professor.id,
        subject=logged_subject,
        body=body,
        body_format=payload.body_format,
        recipient_count=len(recipients),
        sent_at=now,
    )
    db.add(message_log)
    db.commit()
    db.refresh(message_log)

    return ProfessorSessionMessageSendOut(
        message_id=message_log.id,
        session_id=session_obj.id,
        recipient_count=len(recipients),
        sent_at=message_log.sent_at,
    )


@router.post("/professors/me/sessions/{session_id}/absence", response_model=ProfessorSessionOperationOut)
def report_professor_absence(
    session_id: UUID,
    payload: ProfessorMarkAbsenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.PROF)),
) -> ProfessorSessionOperationOut:
    professor = _resolve_professor_profile(db, current_user=current_user)
    permissions = _resolve_professor_permissions(db, professor_id=professor.id)
    if not permissions["can_edit_planning"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Planning edit permission denied")

    session_obj = _require_professor_session(db, professor_id=professor.id, session_id=session_id, lock=True)
    now = _utcnow()

    bookings = db.scalars(
        select(Booking)
        .where(
            Booking.session_id == session_obj.id,
            Booking.status != BookingStatus.CANCELLED,
        )
        .with_for_update()
    ).all()

    refundable_statuses = (BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW, BookingStatus.EXCUSED_ABSENCE)
    notified_students = 0

    for booking in bookings:
        if (
            booking.status in refundable_statuses
            and booking.client_plan_subscription_id is not None
            and session_obj.start_at_utc > now
        ):
            sub_and_plan = _load_subscription_with_plan_for_update(db, subscription_id=booking.client_plan_subscription_id)
            if sub_and_plan is not None:
                subscription, plan = sub_and_plan
                if subscription.user_id == booking.user_id and _is_subscription_active(subscription, plan, now):
                    _restore_pack_credit(subscription, plan)

        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.cancellation_reason = "PROFESSOR_ABSENT"
        skip_pending_reminders_for_booking(
            db,
            booking_id=booking.id,
            reason="Professor absent",
            now=now,
        )

    if payload.notify_students:
        recipient_rows = db.scalars(
            select(User.email)
            .join(Booking, Booking.user_id == User.id)
            .where(
                Booking.session_id == session_obj.id,
                User.email_opt_in.is_(True),
            )
        ).all()
        recipients = sorted({email.strip().lower() for email in recipient_rows if email and email.strip()})

        subject = (payload.students_subject or "").strip() or f"Cours annule - {session_obj.title}"
        body = (payload.students_message or "").strip() or (
            "Le professeur est absent aujourd'hui. "
            "Le cours est annule et vos credits sont restaures si applicable."
        )
        for email in recipients:
            send_session_operation_email(
                to_email=email,
                subject=subject,
                body=body,
                body_format=payload.students_format.value,
                operation="PROF_ABSENCE_CANCEL",
                session_title=session_obj.title,
                sender_user_id=current_user.id,
                sender_label=_display_name(current_user),
                sender_category=CommunicationSenderCategory.PROFESSOR,
                professor_id=professor.id,
            )
        notified_students = len(recipients)
        db.add(
            ProfessorSessionMessage(
                session_id=session_obj.id,
                professor_id=professor.id,
                subject=subject,
                body=body,
                body_format=payload.students_format,
                recipient_count=notified_students,
                sent_at=now,
            )
        )

    session_obj.status = SessionStatus.CANCELLED
    session_obj.cancel_reason = "PROFESSOR_ABSENT"
    session_obj.updated_at = now

    db.commit()

    return ProfessorSessionOperationOut(
        session_id=session_obj.id,
        status=session_obj.status,
        cancel_reason=session_obj.cancel_reason,
        notified_students=notified_students,
    )


@router.post("/bookings/{booking_id}/attendance", response_model=BookingOut)
def update_booking_attendance(
    booking_id: UUID,
    payload: AttendanceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.PROF)),
) -> BookingOut:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    session_obj = db.scalar(select(CourseSession).where(CourseSession.id == booking.session_id).with_for_update())
    if session_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if current_user.role == UserRole.PROF:
        professor = _resolve_professor_profile(db, current_user=current_user)
        permissions = _resolve_professor_permissions(db, professor_id=professor.id)
        if not (permissions["can_take_attendance"] or permissions["can_edit_planning"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Attendance permission denied")
        if session_obj.professor_id != professor.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session does not belong to this professor")

    if booking.status in (BookingStatus.CANCELLED, BookingStatus.WAITLISTED):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking attendance cannot be updated")

    if booking.status not in (
        BookingStatus.BOOKED,
        BookingStatus.ATTENDED,
        BookingStatus.NO_SHOW,
        BookingStatus.EXCUSED_ABSENCE,
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking attendance cannot be updated")

    previous_status = booking.status
    next_status = BookingStatus(payload.attendance_status.value)
    if previous_status != next_status and booking.client_plan_subscription_id is not None:
        sub_and_plan = _load_subscription_with_plan_for_update(db, subscription_id=booking.client_plan_subscription_id)
        if sub_and_plan is not None:
            subscription, plan = sub_and_plan
            if (
                next_status == BookingStatus.EXCUSED_ABSENCE
                and previous_status in (BookingStatus.BOOKED, BookingStatus.ATTENDED, BookingStatus.NO_SHOW)
                and subscription.user_id == booking.user_id
            ):
                _restore_pack_credit(subscription, plan)
            if (
                previous_status == BookingStatus.EXCUSED_ABSENCE
                and next_status in (BookingStatus.ATTENDED, BookingStatus.NO_SHOW)
                and subscription.user_id == booking.user_id
            ):
                if not _consume_pack_credit(subscription, plan):
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient credits to remove excused absence")

    attendance_updated_at = _utcnow()
    if previous_status != next_status and next_status == BookingStatus.EXCUSED_ABSENCE:
        grant_makeup_for_excused_absence(
            db,
            booking=booking,
            actor_user_id=current_user.id,
            now=attendance_updated_at,
        )
    elif previous_status == BookingStatus.EXCUSED_ABSENCE and next_status != BookingStatus.EXCUSED_ABSENCE:
        revoke_pending_makeup_for_corrected_absence(db, booking=booking, now=attendance_updated_at)

    booking.status = next_status
    booking.cancelled_at = None
    booking.cancellation_reason = None

    db.commit()
    db.refresh(booking)

    return _to_booking_out(booking)
