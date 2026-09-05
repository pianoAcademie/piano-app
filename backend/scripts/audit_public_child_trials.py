"""Read-only production audit of public child trial publication and offers."""
from datetime import datetime
import json
from sqlalchemy import select, text
from app.db.session import SessionLocal
from app.models.catalog import Location
from app.models.user import ClientKind
from app.api.routes.catalogue import list_sessions
from app.api.routes.clients import get_public_session_trial_offers

with SessionLocal() as db:
    db.execute(text("SET TRANSACTION READ ONLY"))
    result = []
    for location in db.scalars(select(Location).where(Location.active.is_(True))).all():
        if location.name not in {"Rue d Assas", "Rue d'Assas", "Rue de la Pompe", "Rue de Richelieu", "Rue Dulong", "Rue Scheffer"}:
            continue
        sessions = list_sessions(location_id=location.id, participant_kind=ClientKind.CHILD,
            public_child_trials_only=True, from_=datetime.fromisoformat("2026-09-06T22:00:00+00:00"),
            to=datetime.fromisoformat("2026-09-13T21:59:59+00:00"), timezone="Europe/Paris", db=db)
        for session in sessions:
            if not session.online_booking_enabled or "EXTERNAL" not in session.booking_scopes or session.seats_remaining <= 0:
                continue
            offers = get_public_session_trial_offers(session.id, participant_kind=ClientKind.CHILD, db=db)
            assert offers, f"No child trial offer for {session.id}"
            assert session.public_child_trial_listing_enabled and session.child_trial_bookings_enabled
            result.append({"id":str(session.id), "location":location.name, "start":str(session.start_at_utc),
                "teacher":session.effective_teacher_display_name, "remaining":session.seats_remaining,
                "trial_prices":[str(o.price_ttc) for o in offers]})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result, "No public child trial sessions found"
    db.rollback()
