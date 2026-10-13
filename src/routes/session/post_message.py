# src/routes/session/post_message.py
from src.agentic.agents.chat import continue_wiki_chat
from src.schemas.session_schema import ChatMessageRequest, ChatReplyResponse
from src.routes.session import router
from src.routes.session.storage import _sessions, _sessions_lock, get_session, reply_or_502


@router.post("/{session_id}/messages", response_model=ChatReplyResponse)
def post_message(session_id: str, body: ChatMessageRequest):
    """Schickt eine weitere Nachricht an eine bestehende Chat-Session (per session_id aus start_session)."""
    session = get_session(session_id)
    prev_len = len(session.history)
    session = continue_wiki_chat(
        session,
        body.message,
        active_file=body.active_file,
        active_file_summary=body.active_file_summary,
    )
    with _sessions_lock:
        _sessions[session_id] = session
    return reply_or_502(session, since_index=prev_len)


# Alias
send_message = post_message
