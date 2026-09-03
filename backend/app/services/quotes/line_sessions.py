"""Resolve billing lines to disjoint planning groups, never an activity-wide fallback.

Legacy line UUIDs may have changed when the editor recreated its lines. Recover
only a single unambiguous remaining group; never match by order, price or count.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from fastapi import HTTPException


def _planning_block_signature(block):
    payload = {
        key: str(block.get(key) or "").strip()
        for key in (
            "activity_id",
            "series_key",
            "location_id",
            "weekday",
            "start_time",
            "end_time",
            "start_date",
            "end_date",
            "recurrence_frequency",
        )
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _session_matches_planning_block(session, block, *, original_key=""):
    activity_id = str(block.get("activity_id") or "").strip()
    if str(session.get("activity_id") or "").strip() != activity_id:
        return False

    block_series = str(block.get("series_key") or "").strip()
    session_series = str(session.get("series_key") or "").strip()
    if block_series and session_series:
        return block_series == session_series

    if original_key and str(session.get("recommendation_key") or "").strip() == original_key:
        return True

    comparable = ("location_id", "weekday", "start_time", "end_time")
    meaningful = False
    for key in comparable:
        block_value = str(block.get(key) or "").strip()
        session_value = str(session.get(key) or "").strip()
        if not block_value or not session_value:
            continue
        meaningful = True
        if block_value != session_value:
            return False
    return meaningful


def normalize_duplicate_planning_group_keys(snapshot):
    """Give each planning series for the same activity a stable, disjoint key.

    Older quotes commonly kept the activity UUID on the first block and no key
    (or the same key) on subsequent blocks. That made two weekly slots look like
    one 65-session course to pricing. Keys are derived from the source series
    whenever possible and remain stable across repeated saves.
    """
    normalized = deepcopy(snapshot or {})
    blocks = [dict(item) for item in normalized.get("blocks", []) if isinstance(item, dict)]
    sessions = [dict(item) for item in normalized.get("sessions", []) if isinstance(item, dict)]
    by_activity = defaultdict(list)
    for index, block in enumerate(blocks):
        activity_id = str(block.get("activity_id") or "").strip()
        if activity_id:
            by_activity[activity_id].append(index)

    changed = False
    for activity_id, indexes in by_activity.items():
        if len(indexes) < 2:
            continue
        used = set()
        for index in indexes:
            block = blocks[index]
            original_key = str(block.get("recommendation_key") or "").strip()
            next_key = original_key
            if not next_key or next_key in used:
                series_key = str(block.get("series_key") or "").strip()
                discriminator = series_key or _planning_block_signature(block)
                next_key = f"{activity_id}:series:{discriminator}"
                suffix = 2
                while next_key in used:
                    next_key = f"{activity_id}:series:{discriminator}:{suffix}"
                    suffix += 1
            used.add(next_key)
            if next_key == original_key:
                continue
            block["recommendation_key"] = next_key
            blocks[index] = block
            changed = True
            for session_index, session in enumerate(sessions):
                if _session_matches_planning_block(session, block, original_key=original_key):
                    sessions[session_index] = {**session, "recommendation_key": next_key}

    if changed:
        normalized["blocks"] = blocks
        normalized["sessions"] = sessions
    return normalized, changed


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
