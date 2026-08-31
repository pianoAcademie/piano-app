from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_or_permissions
from app.models.user import User
from app.services.makeup_booking import load_request, options, program

router = APIRouter(prefix="/admin/clients/{student_id}/makeups")


class ProgramRequest(BaseModel):
    session_id: UUID
    expected_version: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get("/{request_id}/options")
def list_options(student_id: UUID, request_id: UUID, start: datetime | None = None, end: datetime | None = None,
                 db: Session = Depends(get_db), _: User = Depends(require_admin_or_permissions("can_edit_planning"))):
    now = datetime.now(timezone.utc)
    start = start or now
    end = end or start + timedelta(days=31)
    if start.tzinfo is None or end.tzinfo is None or end <= start or end - start > timedelta(days=62):
        raise HTTPException(422, "Choisissez une période de recherche de 62 jours maximum, avec fuseau horaire.")
    return options(db, load_request(db, request_id, student_id), now=now, start=start, end=end)


@router.post("/{request_id}/program")
def program_makeup(student_id: UUID, request_id: UUID, payload: ProgramRequest,
                   db: Session = Depends(get_db), actor: User = Depends(require_admin_or_permissions("can_edit_planning"))):
    booking = program(db, request_id=request_id, student_id=student_id, target_id=payload.session_id,
        actor_id=actor.id, expected_version=payload.expected_version)
    db.commit()
    return {"booking_id": booking.id, "session_id": booking.session_id, "additional_amount": "0.00"}
