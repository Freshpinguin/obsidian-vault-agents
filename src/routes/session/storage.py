# src/routes/session/storage.py
import threading

from fastapi import HTTPException

from src.schemas.agent_schema import AgentSession
from src.schemas.session_schema import ChatReplyResponse
from src.core.logging_config import logger

# Chat-Sessions leben nur im Prozessspeicher (kein Neustart-Überstehen, kein Multi-Worker-Betrieb) –
# passend zum Rest der Engine, die ebenfalls ohne externe Datenbank auskommt.
_sessions: dict[str, AgentSession] = {}
_sessions_lock = threading.Lock()


def get_session(session_id: str) -> AgentSession:
    with _sessions_lock:
        session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' nicht gefunden.")
    return session


def reply_or_502(session: AgentSession, since_index: int = 0) -> ChatReplyResponse:
    if not session.is_successful:
        logger.error(f"[ChatAPI] Session {session.session_id} lieferte keine valide Antwort.")
        raise HTTPException(status_code=502, detail="Der Chat-Agent konnte keine Antwort erzeugen.")

    # Mutationen ermitteln, die in diesem Turn ausgeführt wurden
    mutations = []
    mutation_tools = {"create_file", "edit_file", "move_file", "create_directory", "delete_file"}
    for call in session.history[since_index:]:
        if call.tool_calls:
            for tc in call.tool_calls:
                if tc.tool_name in mutation_tools:
                    mutations.append({
                        "tool": tc.tool_name,
                        "path": tc.arguments.get("path") or tc.arguments.get("new_path"),
                        "result": tc.result,
                    })

    return ChatReplyResponse(
        session_id=session.session_id,
        reply=session.final_result.reply,
        mutations=mutations,
    )
