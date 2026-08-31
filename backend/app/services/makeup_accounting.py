"""An absence covered by a pass keeps its charge; its replacement is not a new sale."""

KEY = "makeup_coverage"


def makeup_role(booking):
    coverage = (getattr(booking, "pricing_breakdown_snapshot", None) or {}).get(KEY, {})
    return coverage.get("role") if isinstance(coverage, dict) else None


def mark_original(booking, request):
    booking.pricing_breakdown_snapshot = {
        **(getattr(booking, "pricing_breakdown_snapshot", None) or {}),
        KEY: {"role": "original", "request_id": str(request.id)},
    }
    booking.pricing_snapshot_locked = True


def clear_original(booking):
    breakdown = dict(getattr(booking, "pricing_breakdown_snapshot", None) or {})
    breakdown.pop(KEY, None)
    booking.pricing_breakdown_snapshot = breakdown
