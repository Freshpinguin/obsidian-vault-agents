# src/chat_routes.py
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agents.chat import continue_wiki_chat, start_wiki_chat
from src.schemas.agent_schema import AgentSession
from src.logging_config import logger

router = APIRouter(prefix="/sessions", tags=["chat"])

# Chat-Sessions leben nur im Prozessspeicher (kein Neustart-Überstehen, kein Multi-Worker-Betrieb) –
# passend zum Rest der Engine, die ebenfalls ohne externe Datenbank auskommt.
_sessions: dict[str, AgentSession] = {}
_sessions_lock = threading.Lock()


class StartSessionRequest(BaseModel):
    message: str = Field(min_length=1, description="Die erste Nachricht an den Chat-Agenten.")


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, description="Die nächste Nachricht an den Chat-Agenten.")


class ChatReplyResponse(BaseModel):
    session_id: str
    reply: str


def _get_session(session_id: str) -> AgentSession:
    with _sessions_lock:
        session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' nicht gefunden.")
    return session


def _reply_or_502(session: AgentSession) -> ChatReplyResponse:
    if not session.is_successful:
        logger.error(f"[ChatAPI] Session {session.session_id} lieferte keine valide Antwort.")
        raise HTTPException(status_code=502, detail="Der Chat-Agent konnte keine Antwort erzeugen.")
    return ChatReplyResponse(session_id=session.session_id, reply=session.final_result.reply)


@router.post("", response_model=ChatReplyResponse, status_code=201)
def start_session(body: StartSessionRequest):
    """Erstellt eine neue Chat-Session mit der ersten Nachricht und behält sie im Speicher."""
    session = start_wiki_chat(body.message)
    with _sessions_lock:
        _sessions[session.session_id] = session
    return _reply_or_502(session)


@router.post("/{session_id}/messages", response_model=ChatReplyResponse)
def send_message(session_id: str, body: ChatMessageRequest):
    """Schickt eine weitere Nachricht an eine bestehende Chat-Session (per session_id aus start_session)."""
    session = _get_session(session_id)
    session = continue_wiki_chat(session, body.message)
    with _sessions_lock:
        _sessions[session_id] = session
    return _reply_or_502(session)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str):
    """Löscht eine Chat-Session aus dem Speicher."""
    with _sessions_lock:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' nicht gefunden.")
        del _sessions[session_id]
