# src/agentic/engine/session_log.py
import os
import glob
from datetime import datetime
from typing import TYPE_CHECKING

from src.core.logging_config import logger, LOG_DIR

if TYPE_CHECKING:
    from src.schemas.agent_schema import AgentSession, LLMCall

LLM_DIR = os.path.join(LOG_DIR, "llm_details")
os.makedirs(LLM_DIR, exist_ok=True)
MAX_SESSION_LOGS = 100


def _cleanup_old_session_logs():
    """Keeps only the most recent MAX_SESSION_LOGS session log files."""
    files = sorted(glob.glob(os.path.join(LLM_DIR, "*.md")), key=os.path.getmtime)
    while len(files) > MAX_SESSION_LOGS:
        oldest_file = files.pop(0)
        try:
            os.remove(oldest_file)
        except Exception as e:
            logger.error(f"Could not delete old session log {oldest_file}: {e}")


class SessionLogger:
    """Collects the entire history of an AgentSession (every LLM turn, every tool
    call) in a single Markdown log file, instead of creating one file per LLM call as
    it used to. The file is created when the session starts and appended to on every
    turn, so that even if the process crashes in the middle of a long ReAct loop,
    everything up to that point is already on disk.

    For chat agents, where the same session lives on across several user messages,
    'existing_path' attaches to the same file instead of creating another one per
    message - a session therefore ALWAYS stays exactly one log file, regardless of how
    many turns it has.
    """

    def __init__(self, agent_name: str, session_id: str, existing_path: str | None = None):
        if existing_path and os.path.exists(existing_path):
            self.filepath = existing_path
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(LLM_DIR, f"{timestamp}_{agent_name}_{session_id}.md")

        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(f"# Agent Session: {agent_name} ({session_id})\n\n")
            f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n")

        _cleanup_old_session_logs()

    def log_step(self, step: int, call: "LLMCall", messages: list[dict], model: str, raw_response: str, tokens_in: int, tokens_out: int):
        """Logs one LLM turn: the complete context sent at that point (assembled from
        the session), the raw model response and any executed tool calls with their
        results. 'step' counts continuously across the whole session (not just the
        current turn), so the numbering stays unambiguous for chat sessions with
        several messages."""
        prompt_text = "\n\n".join(
            f"[{m['role'].upper()}]\n{m.get('content') or ''}" for m in messages
        )

        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"## Step {step} — {model} — {call.status.upper()}\n\n")
            f.write(f"**Tokens In:** {tokens_in} | **Tokens Out:** {tokens_out}\n\n")
            f.write(f"### Context (complete history up to this turn)\n\n{prompt_text}\n\n")
            f.write(f"### Raw response\n\n{raw_response}\n\n")
            if call.tool_calls:
                f.write("### Tool calls\n\n")
                for tc in call.tool_calls:
                    f.write(f"- **{tc.tool_name}**(`{tc.arguments}`)\n\n  → {tc.result}\n\n")
            f.write("---\n\n")

    def log_api_error(self, step: int, model: str, messages: list[dict], error: str):
        prompt_text = "\n\n".join(
            f"[{m['role'].upper()}]\n{m.get('content') or ''}" for m in messages
        )
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"## Step {step} — {model} — API ERROR\n\n")
            f.write(f"### Context (complete history up to this turn)\n\n{prompt_text}\n\n")
            f.write(f"### Error\n\n{error}\n\n---\n\n")

    def log_compaction(self, step: int, before_chars: int, after_chars: int, compacted_count: int, summary: str):
        """Logs a context compaction (see compaction.py) - important for traceability,
        since the context the model actually sees from here on differs from the
        previous step."""
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"## Context compaction before step {step}\n\n")
            f.write(f"Compacted {compacted_count} messages: {before_chars} -> {after_chars} chars.\n\n")
            f.write(f"### Summary\n\n{summary}\n\n---\n\n")

    def log_turn_end(self, session: "AgentSession"):
        """Writes an interim summary to the end of the log file - for one-shot agents
        the final conclusion, for chat agents the state after the current turn (the
        file simply continues on the next turn)."""
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write("## Result (state so far)\n\n")
            f.write("✅ Last turn succeeded\n" if session.is_successful else "❌ Last turn failed\n")
            f.write(f"\nTurns gesamt: {len(session.history)} | davon Tool-Aufrufe: {session.tool_steps}\n\n---\n\n")
