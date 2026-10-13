# src/routes/session/delete_session.py
from fastapi import HTTPException

from src.routes.session import router
from src.routes.session.storage import _sessions, _sessions_lock


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str):
    """Löscht eine Chat-Session aus dem Speicher."""
    with _sessions_lock:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' nicht gefunden.")
        del _sessions[session_id]
