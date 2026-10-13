from fastapi import Request
from src.agentic import start_wiki_chat
from src.schemas.session_schema import ChatReplyResponse, StartSessionRequest
from src.routes.session import router
from src.routes.session.storage import _sessions, _sessions_lock, reply_or_502, stream_chat_session


@router.post("", response_model=ChatReplyResponse, status_code=201)
def post_session(body: StartSessionRequest, request: Request):
    """Creates a new chat session with the first message and keeps it in memory."""
    if "text/event-stream" in request.headers.get("accept", ""):
        return stream_chat_session(
            lambda on_status: start_wiki_chat(
                body.message,
                active_file=body.active_file,
                active_file_summary=body.active_file_summary,
                on_status=on_status,
            ),
            status_code=201,
        )

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
