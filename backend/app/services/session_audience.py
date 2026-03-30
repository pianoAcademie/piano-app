from __future__ import annotations

from collections.abc import Iterable

from app.models.catalog import CourseSession, SessionAudienceScope
from app.models.plan import PlanKind

NON_PRIVATE_SESSION_AUDIENCES: tuple[SessionAudienceScope, ...] = (
    SessionAudienceScope.EXTERNAL,
    SessionAudienceScope.SUBSCRIPTION,
    SessionAudienceScope.FORFAIT,
)
SESSION_AUDIENCE_ORDER: tuple[SessionAudienceScope, ...] = (
    SessionAudienceScope.EXTERNAL,
    SessionAudienceScope.SUBSCRIPTION,
    SessionAudienceScope.FORFAIT,
    SessionAudienceScope.PRIVATE,
)


def _coerce_scope_token(raw: object | None) -> SessionAudienceScope | None:
    if isinstance(raw, SessionAudienceScope):
        return raw
    value = str(raw or "").strip().upper()
    if value == SessionAudienceScope.EXTERNAL.value:
        return SessionAudienceScope.EXTERNAL
    if value == SessionAudienceScope.SUBSCRIPTION.value:
        return SessionAudienceScope.SUBSCRIPTION
    if value == SessionAudienceScope.FORFAIT.value:
        return SessionAudienceScope.FORFAIT
    if value == SessionAudienceScope.PRIVATE.value:
        return SessionAudienceScope.PRIVATE
    return None


def normalize_session_audience_scope(
    raw: SessionAudienceScope | str | None,
    *,
    fallback: SessionAudienceScope = SessionAudienceScope.EXTERNAL,
) -> SessionAudienceScope:
    return _coerce_scope_token(raw) or fallback


def _iter_scope_tokens(raw: object | None) -> Iterable[object]:
    if raw is None:
        return ()
    if isinstance(raw, SessionAudienceScope):
        return (raw,)
    if isinstance(raw, str):
        return tuple(token for token in raw.split(","))
    if isinstance(raw, Iterable):
        return raw
    return (raw,)


def normalize_session_audience_scopes(
    raw: object | None,
    *,
    fallback: Iterable[SessionAudienceScope | str] | SessionAudienceScope | str | None = None,
) -> list[SessionAudienceScope]:
    seen: set[SessionAudienceScope] = set()
    normalized: list[SessionAudienceScope] = []
    for token in _iter_scope_tokens(raw):
        scope = _coerce_scope_token(token)
        if scope is None or scope in seen:
            continue
        seen.add(scope)
        normalized.append(scope)

    if SessionAudienceScope.PRIVATE in seen:
        return [SessionAudienceScope.PRIVATE]

    ordered = [scope for scope in SESSION_AUDIENCE_ORDER if scope in seen and scope != SessionAudienceScope.PRIVATE]
    if ordered:
        return ordered

    if fallback is None:
        return [SessionAudienceScope.EXTERNAL]
    if fallback is raw:
        return [SessionAudienceScope.EXTERNAL]
    return normalize_session_audience_scopes(fallback, fallback=None)


def serialize_session_audience_scopes(scopes: object | None) -> str:
    normalized = normalize_session_audience_scopes(scopes)
    return ",".join(scope.value for scope in normalized)


def primary_session_audience_scope(
    scopes: object | None,
    *,
    fallback: SessionAudienceScope = SessionAudienceScope.EXTERNAL,
) -> SessionAudienceScope:
    normalized = normalize_session_audience_scopes(scopes, fallback=fallback)
    return normalized[0] if normalized else fallback


def legacy_visibility_scope(*, is_private: bool) -> list[SessionAudienceScope]:
    return [SessionAudienceScope.PRIVATE] if bool(is_private) else [SessionAudienceScope.EXTERNAL]


def legacy_booking_scope(*, is_private: bool, allow_online_booking: bool) -> list[SessionAudienceScope]:
    if bool(is_private) or not bool(allow_online_booking):
        return [SessionAudienceScope.PRIVATE]
    return [SessionAudienceScope.EXTERNAL]


def resolve_session_visibility_scopes(session_obj: CourseSession) -> list[SessionAudienceScope]:
    return normalize_session_audience_scopes(
        getattr(session_obj, "visibility_scope", None),
        fallback=legacy_visibility_scope(is_private=bool(getattr(session_obj, "is_private", False))),
    )


def resolve_session_booking_scopes(
    session_obj: CourseSession,
    *,
    allows_student_bookings: bool | None = None,
) -> list[SessionAudienceScope]:
    visibility_scopes = resolve_session_visibility_scopes(session_obj)
    booking_scopes = normalize_session_audience_scopes(
        getattr(session_obj, "booking_scope", None),
        fallback=legacy_booking_scope(
            is_private=bool(getattr(session_obj, "is_private", False)),
            allow_online_booking=bool(getattr(session_obj, "allow_online_booking", False)),
        ),
    )
    return coerce_booking_scopes(
        visibility_scopes=visibility_scopes,
        booking_scopes=booking_scopes,
        allows_student_bookings=allows_student_bookings,
    )


def resolve_session_visibility_scope(session_obj: CourseSession) -> SessionAudienceScope:
    return primary_session_audience_scope(resolve_session_visibility_scopes(session_obj))


def resolve_session_booking_scope(
    session_obj: CourseSession,
    *,
    allows_student_bookings: bool | None = None,
) -> SessionAudienceScope:
    return primary_session_audience_scope(
        resolve_session_booking_scopes(session_obj, allows_student_bookings=allows_student_bookings),
        fallback=SessionAudienceScope.PRIVATE,
    )


def coerce_booking_scopes(
    *,
    visibility_scopes: object | None,
    booking_scopes: object | None,
    allows_student_bookings: bool | None,
) -> list[SessionAudienceScope]:
    resolved_visibility = normalize_session_audience_scopes(visibility_scopes)
    resolved_booking = normalize_session_audience_scopes(
        booking_scopes,
        fallback=[SessionAudienceScope.EXTERNAL],
    )
    if SessionAudienceScope.PRIVATE in resolved_visibility:
        return [SessionAudienceScope.PRIVATE]
    if allows_student_bookings is False:
        return [SessionAudienceScope.PRIVATE]
    if SessionAudienceScope.PRIVATE in resolved_booking:
        return [SessionAudienceScope.PRIVATE]
    return resolved_booking


def coerce_session_scope_sets(
    *,
    visibility_scopes: object | None,
    booking_scopes: object | None,
    allows_student_bookings: bool | None,
    fallback_is_private: bool = False,
    fallback_allow_online_booking: bool = True,
) -> tuple[list[SessionAudienceScope], list[SessionAudienceScope]]:
    resolved_visibility = normalize_session_audience_scopes(
        visibility_scopes,
        fallback=legacy_visibility_scope(is_private=fallback_is_private),
    )
    resolved_booking = normalize_session_audience_scopes(
        booking_scopes,
        fallback=legacy_booking_scope(
            is_private=fallback_is_private,
            allow_online_booking=fallback_allow_online_booking,
        ),
    )
    resolved_booking = coerce_booking_scopes(
        visibility_scopes=resolved_visibility,
        booking_scopes=resolved_booking,
        allows_student_bookings=allows_student_bookings,
    )
    return resolved_visibility, resolved_booking


def coerce_booking_scope(
    *,
    visibility_scope: SessionAudienceScope,
    booking_scope: SessionAudienceScope,
    allows_student_bookings: bool | None,
) -> SessionAudienceScope:
    return primary_session_audience_scope(
        coerce_booking_scopes(
            visibility_scopes=[visibility_scope],
            booking_scopes=[booking_scope],
            allows_student_bookings=allows_student_bookings,
        ),
        fallback=SessionAudienceScope.PRIVATE,
    )


def coerce_session_scopes(
    *,
    visibility_scope: SessionAudienceScope | str | None,
    booking_scope: SessionAudienceScope | str | None,
    allows_student_bookings: bool | None,
    fallback_is_private: bool = False,
    fallback_allow_online_booking: bool = True,
) -> tuple[SessionAudienceScope, SessionAudienceScope]:
    visibility_scopes, booking_scopes = coerce_session_scope_sets(
        visibility_scopes=[visibility_scope] if visibility_scope is not None else None,
        booking_scopes=[booking_scope] if booking_scope is not None else None,
        allows_student_bookings=allows_student_bookings,
        fallback_is_private=fallback_is_private,
        fallback_allow_online_booking=fallback_allow_online_booking,
    )
    return (
        primary_session_audience_scope(visibility_scopes),
        primary_session_audience_scope(booking_scopes, fallback=SessionAudienceScope.PRIVATE),
    )


def legacy_flags_from_scopes(
    *,
    visibility_scope: SessionAudienceScope | None = None,
    booking_scope: SessionAudienceScope | None = None,
    visibility_scopes: object | None = None,
    booking_scopes: object | None = None,
    allows_student_bookings: bool | None,
) -> tuple[bool, bool]:
    resolved_visibility = normalize_session_audience_scopes(
        visibility_scopes if visibility_scopes is not None else ([visibility_scope] if visibility_scope is not None else None),
        fallback=[SessionAudienceScope.EXTERNAL],
    )
    resolved_booking = coerce_booking_scopes(
        visibility_scopes=resolved_visibility,
        booking_scopes=booking_scopes if booking_scopes is not None else ([booking_scope] if booking_scope is not None else None),
        allows_student_bookings=allows_student_bookings,
    )
    is_private = resolved_visibility == [SessionAudienceScope.PRIVATE]
    allow_online_booking = resolved_booking != [SessionAudienceScope.PRIVATE]
    return is_private, allow_online_booking


def scope_allows_external_visibility(scope: SessionAudienceScope | str | None) -> bool:
    return SessionAudienceScope.EXTERNAL in normalize_session_audience_scopes(scope)


def scopes_allow_external_visibility(scopes: object | None) -> bool:
    return SessionAudienceScope.EXTERNAL in normalize_session_audience_scopes(scopes)


def scope_allows_planless_booking(scope: SessionAudienceScope | str | None) -> bool:
    return scopes_allow_planless_booking([normalize_session_audience_scope(scope)])


def scopes_allow_planless_booking(scopes: object | None) -> bool:
    resolved_scopes = normalize_session_audience_scopes(scopes, fallback=[SessionAudienceScope.PRIVATE])
    if resolved_scopes == [SessionAudienceScope.PRIVATE]:
        return False
    return SessionAudienceScope.EXTERNAL in resolved_scopes


def _normalized_plan_kind(plan_kind: PlanKind | str | None) -> PlanKind | None:
    try:
        return plan_kind if isinstance(plan_kind, PlanKind) else PlanKind(str(plan_kind or "").strip().upper())
    except ValueError:
        return None


def scope_allows_plan_kind(
    scope: SessionAudienceScope | str | None,
    *,
    plan_kind: PlanKind | str | None,
) -> bool:
    return scopes_allow_plan_kind([normalize_session_audience_scope(scope)], plan_kind=plan_kind)


def scopes_allow_plan_kind(
    scopes: object | None,
    *,
    plan_kind: PlanKind | str | None,
) -> bool:
    normalized_kind = _normalized_plan_kind(plan_kind)
    if normalized_kind is None:
        return False
    return normalized_kind in allowed_plan_kinds_for_scopes(scopes)


def allowed_plan_kinds_for_scope(
    scope: SessionAudienceScope | str | None,
) -> set[PlanKind]:
    return allowed_plan_kinds_for_scopes([normalize_session_audience_scope(scope)])


def allowed_plan_kinds_for_scopes(
    scopes: object | None,
) -> set[PlanKind]:
    resolved_scopes = normalize_session_audience_scopes(scopes, fallback=[SessionAudienceScope.PRIVATE])
    if resolved_scopes == [SessionAudienceScope.PRIVATE]:
        return set()

    allowed: set[PlanKind] = set()
    if SessionAudienceScope.EXTERNAL in resolved_scopes:
        allowed.update({PlanKind.PACK, PlanKind.SUBSCRIPTION, PlanKind.FORFAIT})
    if SessionAudienceScope.SUBSCRIPTION in resolved_scopes:
        allowed.update({PlanKind.PACK, PlanKind.SUBSCRIPTION})
    if SessionAudienceScope.FORFAIT in resolved_scopes:
        allowed.add(PlanKind.FORFAIT)
    return allowed
