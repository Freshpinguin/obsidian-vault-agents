# src/routes/session/storage.py
import json
import queue
import threading
from typing import Callable

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from src.schemas.agent_schema import AgentSession
from src.schemas.session_schema import ChatReplyResponse
from src.core.logging_config import logger
from src.agentic import session_failure_detail

# Chat sessions live only in process memory (they do not survive a restart and do not
# work across multiple workers) - in keeping with the rest of the engine, which also
# gets by without an external database.
_sessions: dict[str, AgentSession] = {}
_sessions_lock = threading.Lock()


def get_session(session_id: str) -> AgentSession:
    with _sessions_lock:
        session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session


def extract_mutations(session: AgentSession, since_index: int = 0) -> list[dict]:
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
    return mutations


def reply_or_502(session: AgentSession, since_index: int = 0) -> ChatReplyResponse:
    if not session.is_successful:
        logger.error(f"[ChatAPI] Session {session.session_id} did not return a valid response.")
        # The classified reason (provider 500, rate limit, timeout, ...) instead of a
        # generic sentence - the frontend shows this detail verbatim in the chat.
        raise HTTPException(status_code=502, detail=session_failure_detail(session))

    return ChatReplyResponse(
        session_id=session.session_id,
        reply=session.final_result.reply,
        mutations=extract_mutations(session, since_index=since_index),
    )


def stream_chat_session(
    run_func: Callable[[Callable[[str, str], None]], AgentSession],
    since_index: int = 0,
    existing_session_id: str | None = None,
    status_code: int = 200,
) -> StreamingResponse:
    q: queue.Queue = queue.Queue()

    def status_callback(msg: str, level: str = "info") -> None:
        # level is "warning" while a turn is degraded but still running (provider retry
        # or failover), so the frontend can mark it instead of showing plain progress.
        q.put({"type": "status", "message": msg, "level": level})

    def worker() -> None:
        try:
            session = run_func(status_callback)
            if not session.is_successful:
                q.put({"type": "error", "detail": session_failure_detail(session)})
                return

            sess_id = existing_session_id or session.session_id
            with _sessions_lock:
                _sessions[sess_id] = session

            mutations = extract_mutations(session, since_index=since_index)
            q.put({
                "type": "done",
                "session_id": sess_id,
                "reply": session.final_result.reply,
                "mutations": mutations,
            })
        except Exception as e:
            logger.error(f"[ChatAPI] Error while streaming: {e}", exc_info=True)
            q.put({"type": "error", "detail": str(e)})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_generator():
        while True:
            event = q.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        status_code=status_code,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
