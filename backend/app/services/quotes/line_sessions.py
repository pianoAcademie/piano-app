"""Resolve billing lines to disjoint planning groups, never an activity-wide fallback.

Legacy line UUIDs may have changed when the editor recreated its lines. Recover
only a single unambiguous remaining group; never match by order, price or count.
"""
from collections import defaultdict
from fastapi import HTTPException


def line_planning_key(line, *, force_line_key=False):
    activity = str(getattr(line, "activity_id", None) or "").strip()
    if not activity:
        return ""
    meta = getattr(line, "meta", None) or {}
    explicit = str(meta.get("recommendation_key") or meta.get("line_recommendation_key") or "").strip()
    if explicit:
        return explicit
    source = str(meta.get("typeform_automatic_line") or "").strip()
    if source:
        return f"{activity}:{source}"
    line_id = str(getattr(line, "id", None) or "").strip()
    return f"{activity}:line:{line_id}" if force_line_key and line_id else activity


def resolve_line_sessions(lines, snapshot):
    """Return (line, sessions, stable_key) without mutating inputs.

    No sessions for an activity means it is off-planning. Multiple billing lines
    must each have a unique group, including manually priced lines.
    """
    by_activity = defaultdict(list)
    groups = defaultdict(lambda: defaultdict(list))
    for line in lines:
        if (getattr(line, "activity_id", None) and getattr(line, "line_category", None) == "service"
                and getattr(line, "line_type", None) == "item"):
            by_activity[str(line.activity_id)].append(line)
    for session in (snapshot or {}).get("sessions", []):
        if not isinstance(session, dict) or not session.get("activity_id"):
            continue
        activity = str(session["activity_id"])
        key = str(session.get("recommendation_key") or activity).strip()
        groups[activity][key].append(session)
    result = []
    for activity, activity_lines in by_activity.items():
        available = groups[activity]
        if not available:
            continue
        claimed = set()
        unresolved = []
        for line in activity_lines:
            key = line_planning_key(line, force_line_key=len(activity_lines) > 1)
            if key in available:
                if key in claimed:
                    _ambiguous()
                claimed.add(key)
                result.append((line, available[key], key))
            else:
                unresolved.append(line)
        remaining = set(available) - claimed
        if not unresolved and not remaining:
            continue
        if len(unresolved) == 1:
            line = unresolved[0]
            meta = getattr(line, "meta", None) or {}
            explicit = meta.get("recommendation_key") or meta.get("line_recommendation_key")
            automatic = meta.get("typeform_automatic_line")
            # The only legacy aggregate fallback allowed: a single billing line
            # and an entirely unkeyed planning, even if the line has a source tag.
            if len(activity_lines) == 1 and set(available) == {activity} and not explicit:
                result.append((line, available[activity], activity))
                continue
            if not explicit and not automatic and len(remaining) == 1:
                key = next(iter(remaining))
                result.append((line, available[key], key))
                continue
            if len(activity_lines) == 1 and not explicit and not automatic:
                result.append((line, [s for group in available.values() for s in group], None))
                continue
        _ambiguous()
    return result


def _ambiguous():
    raise HTTPException(409, "Rattachement ambigu entre les lignes facturées et les créneaux. "
                        "Vérifiez chaque cours dans les activités planifiées avant d'enregistrer ; "
                        "aucune quantité ne peut être regroupée automatiquement.")
