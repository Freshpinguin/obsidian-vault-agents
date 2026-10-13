# src/routes/session/post_session.py
from src.agentic.agents.chat import start_wiki_chat
from src.schemas.session_schema import ChatReplyResponse, StartSessionRequest
from src.routes.session import router
from src.routes.session.storage import _sessions, _sessions_lock, reply_or_502


@router.post("", response_model=ChatReplyResponse, status_code=201)
def post_session(body: StartSessionRequest):
    """Erstellt eine neue Chat-Session mit der ersten Nachricht und behält sie im Speicher."""
    session = start_wiki_chat(
        body.message,
        active_file=body.active_file,
        active_file_summary=body.active_file_summary,
    )
    with _sessions_lock:
        _sessions[session.session_id] = session
    return reply_or_502(session)


# Alias
start_session = post_session
