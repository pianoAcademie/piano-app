from copy import deepcopy
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import case, select

from app.models.learning_progress import StudentLearningProgress
from app.models.repertoire import StudentSheetMusic


def initial_learning_state(assignments):
    # No inferred piece completions or historical learning dates.
    books = {}
    current = None
    for row in assignments:
        if row.product_id is None:
            continue
        key = str(row.product_id)
        books.setdefault(key, {"current_piece_id": str(row.current_piece_id) if row.current_piece_id else None,
                               "pieces": {}, "completed": row.status == "COMPLETED",
                               "note": getattr(row, "internal_note", None) or ""})
        if current is None and row.status in {"IN_PROGRESS", "DELIVERED"}:
            current = key
    return {"product_id": current, "books": books}


def learning_snapshot(db, student_id):
    row = db.get(StudentLearningProgress, student_id)
    if row is not None:
        return {"revision": row.revision, "state": row.state}
    assignments = db.scalars(select(StudentSheetMusic).where(StudentSheetMusic.student_id == student_id)
        .order_by(case((StudentSheetMusic.status == "IN_PROGRESS", 0), else_=1), StudentSheetMusic.created_at.desc())).all()
    return {"revision": 0, "state": initial_learning_state(assignments)}


def apply_learning_change(state, *, action, product_id, piece_id, statuses, catalog, session_id, now=None):
    """Pure transition; callers lock the student and enforce access/revision."""
    result = deepcopy(state)
    books = result["books"]
    active_id = result.get("product_id")
    if action in {"CORRECT", "HISTORY", "NEXT_BOOK"}:
        if product_id not in catalog:
            raise HTTPException(422, "Choisissez une partition active.")
        allowed = catalog[product_id]
        if piece_id and piece_id not in allowed:
            raise HTTPException(422, "Ce morceau n’appartient pas à la partition.")
        if action == "NEXT_BOOK":
            previous = books.get(active_id, {})
            if not previous.get("completed") or product_id == active_id:
                raise HTTPException(409, "Terminez la partition actuelle avant de passer à la suivante.")
        book = books.setdefault(product_id, {"pieces": {}, "current_piece_id": None, "completed": False})
        if statuses is not None:
            for key, status in statuses.items():
                if key not in allowed or status not in {"UNKNOWN", "REVIEW", "COMPLETED"}:
                    raise HTTPException(422, "Historique des morceaux invalide.")
                old = book["pieces"].get(key, {})
                if old.get("status", "UNKNOWN") != status:
                    # A baseline is a declaration, not a dated lesson completion.
                    book["pieces"][key] = {"status": status, "source": "BASELINE", "completed_at": None}
        book["current_piece_id"] = piece_id
        book["completed"] = False
        # A previously completed piece can be revisited without erasing its completion.
        result["product_id"] = product_id
    elif action in {"CONTINUE", "COMPLETE_PIECE", "COMPLETE_BOOK"}:
        if active_id not in catalog or active_id not in books:
            raise HTTPException(422, "Renseignez d’abord la partition actuelle.")
        book = books[active_id]
        allowed = catalog[active_id]
        current = book.get("current_piece_id")
        if action in {"CONTINUE", "COMPLETE_PIECE"}:
            if current not in allowed or book.get("completed"):
                raise HTTPException(422, "Renseignez le morceau actuellement travaillé.")
        if action == "COMPLETE_PIECE":
            if piece_id == current or (piece_id and piece_id not in allowed):
                raise HTTPException(422, "Choisissez un autre morceau de cette partition.")
            remaining = [key for key in allowed if key != current and book["pieces"].get(key, {}).get("status") != "COMPLETED"]
            if remaining and not piece_id:
                raise HTTPException(422, "Choisissez le prochain morceau ; certains restent à vérifier ou à reprendre.")
            book["pieces"][current] = {"status": "COMPLETED", "source": "LESSON",
                "completed_at": (now or datetime.now(timezone.utc)).isoformat(), "session_id": str(session_id)}
            book["current_piece_id"] = piece_id
        if action == "COMPLETE_BOOK":
            if not allowed or any(book["pieces"].get(key, {}).get("status") != "COMPLETED" for key in allowed):
                raise HTTPException(422, "Des morceaux restent à vérifier ou à terminer.")
            book["completed"] = True
            book["current_piece_id"] = None
    else:
        raise HTTPException(422, "Action inconnue.")
    return result
