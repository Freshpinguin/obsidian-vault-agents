# src/agentic/engine/guards.py
"""Safety checks and hallucination detection for the agent ReAct loop."""
from typing import Any
from src.schemas.status import AgentStatus
from src.schemas.tool_schema import MUTATION_TOOL_NAMES

# Phrases that indicate the model is claiming (or announcing) a vault mutation.
# These are matched against the reply text, so they must stay in the same
# language the agents are prompted to answer in.
MUTATION_INDICATORS = [
    "created", "saved", "edited", "updated", "moved", "renamed", "deleted", "removed",
    "i'll create", "i will create", "i'll add", "i will add", "i'll save", "i will save",
    "i'm creating", "i am creating", "i'll delete", "i will delete", "i'll move",
    "i will move", "let me create", "has been written", "i've written",
]

# Negated or failed mutations must not count as a hallucinated claim.
NEGATIONS = [
    "not created", "no file", "could not", "couldn't", "was unable", "wasn't able",
    "not possible", "not found", "does not exist", "doesn't exist", "not deleted",
    "not saved", "failed to",
]

SKIPPED_REQUIRED_TOOL_ERROR = (
    "Your response was rejected: for this task you must call at least one tool "
    "(e.g. update_plan) before giving a final answer. Call the appropriate tool now "
    "instead of answering directly."
)

HALLUCINATED_MUTATION_ERROR = (
    "Your response was rejected: in your reply text you claimed or announced that you would "
    "create or modify a file or folder, but you did NOT execute a corresponding tool "
    "(e.g. create_file, edit_file) as a tool call. Nothing was written to the vault. "
    "In your next step, call the appropriate tool (e.g. create_file) as a function call FIRST."
)


def check_skipped_required_tool(agent: Any, tool_steps: int) -> bool:
    """The model skipped the required 'use at least one tool first' step and jumped
    straight to a (possibly entirely hallucinated) final answer. Despite being valid
    JSON this must not count as success; treat it like a parse error instead."""
    return bool(getattr(agent, "require_tool_call_first_round", False) and tool_steps == 0)


def check_hallucinated_mutation(agent: Any, parse_result: Any, tool_steps: int) -> bool:
    """Checks whether the agent claimed or announced a file modification in its text
    without ever having called a corresponding tool (e.g. create_file, edit_file)."""
    if tool_steps != 0:
        return False

    status = getattr(parse_result, "status", None)
    if status != AgentStatus.SUCCESS:
        return False

    agent_tools = getattr(agent, "tools", []) or []
    has_mutation_tools = any(getattr(t, "name", None) in MUTATION_TOOL_NAMES for t in agent_tools)
    if not has_mutation_tools:
        return False

    reply_text = ""
    parsed_data = getattr(parse_result, "parsed_data", None)
    if hasattr(parsed_data, "reply"):
        reply_text = str(parsed_data.reply).lower()
    elif isinstance(parsed_data, dict):
        reply_text = str(parsed_data.get("reply", "")).lower()

    if any(ind in reply_text for ind in MUTATION_INDICATORS) and (
        ".md" in reply_text or "file" in reply_text or "folder" in reply_text
        or "note" in reply_text or "directory" in reply_text
    ):
        if not any(neg in reply_text for neg in NEGATIONS):
            return True

    return False
