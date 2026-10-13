# src/agentic/engine/response.py
"""Helpers for processing and cleaning up LLM responses."""


def strip_json_fence(text: str) -> str:
    """Removes a surrounding Markdown code fence (```json ... ```) if the model
    emits one despite instructions. Only relevant when no response_format is
    enforced (i.e. in the tool-calling case), otherwise a no-op."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[1] if "\n" in text else ""
    if body.endswith("```"):
        body = body[:-3]
    return body.strip()
