"""Read-only digest for comparing ordinary public calendars before a rollout."""
from datetime import datetime
import hashlib
import json
from sqlalchemy import text
from app.db.session import SessionLocal
from app.api.routes.catalogue import list_sessions
from app.models.user import ClientKind

with SessionLocal() as db:
    db.execute(text("SET TRANSACTION READ ONLY"))
    for kind in (None, ClientKind.CHILD, ClientKind.ADULT):
        sessions = list_sessions(participant_kind=kind,
            from_=datetime.fromisoformat("2026-09-06T22:00:00+00:00"),
            to=datetime.fromisoformat("2026-09-13T21:59:59+00:00"), timezone="Europe/Paris", db=db)
        rows = []
        for session in sessions:
            row = session.model_dump(mode="json")
            row.pop("public_child_trial_listing_enabled", None)
            row["course_type"].pop("trial_course_price_ttc", None)
            rows.append(row)
        encoded = json.dumps(sorted(rows, key=lambda r:r["id"]), sort_keys=True).encode()
        print(kind, len(rows), hashlib.sha256(encoded).hexdigest())
    db.rollback()
