# src/agentic/engine/api_errors.py
"""Turns provider exceptions into text a user can act on.

The raw errors are useless in the UI: a Gemini 500 arrives as a litellm
APIConnectionError wrapping an InternalServerError wrapping a JSON body, followed by a
stack trace. The full version belongs in the session log (see SessionLogger), while the
chat needs one sentence that says what happened, whether the vault was touched, and
whether retrying is worth it.
"""
import litellm

from src.schemas.status import AgentStatus

# Shown while a call is being retried, so a stalled turn does not look like a hang.
RETRY_STATUS = "The AI provider is unavailable ({reason}) - retrying ({attempt}/{total})…"
FAILOVER_STATUS = "The AI provider failed ({reason}) - switching to the fallback model ({model})…"

_NOTHING_WRITTEN = "Nothing was written to the vault."
_TRY_AGAIN = "Please try again in a moment."


# A turn can also end without a provider error: the model kept returning unparsable or
# rejected answers until max_retries ran out.
PARSE_FAILURE_MESSAGE = (
    "The AI model did not return a usable answer after several attempts. "
    f"{_NOTHING_WRITTEN} {_TRY_AGAIN}"
)
GENERIC_FAILURE_MESSAGE = f"The chat agent could not produce a response. {_NOTHING_WRITTEN} {_TRY_AGAIN}"


def session_failure_detail(session) -> str:
    """The user-facing reason a turn produced no answer, for the chat UI and the 502
    response. Falls back to a generic sentence if the session carries no classified
    error (which should not happen, but must never hide the failure itself)."""
    last = session.history[-1] if session.history else None
    if last is not None and last.status == AgentStatus.ERROR:
        return last.user_message or PARSE_FAILURE_MESSAGE
    return GENERIC_FAILURE_MESSAGE


def short_reason(exc: BaseException) -> str:
    """A two or three word label for the status line (not a whole sentence)."""
    if isinstance(exc, litellm.RateLimitError):
        return "rate limit"
    if isinstance(exc, litellm.Timeout):
        return "timeout"
    if isinstance(exc, litellm.ServiceUnavailableError) or _mentions(exc, "503", "unavailable", "overloaded"):
        return "overloaded"
    if isinstance(exc, litellm.InternalServerError) or _mentions(exc, "internalservererror", "500"):
        return "server error"
    if isinstance(exc, litellm.APIConnectionError):
        return "connection failed"
    return "error"


def describe_api_failure(exc: BaseException) -> str:
    """One self-contained sentence for the chat, after every retry has been used up."""
    if isinstance(exc, litellm.RateLimitError):
        return (
            f"The AI provider's rate limit has been reached for every available model. "
            f"{_NOTHING_WRITTEN} Please wait a moment before trying again."
        )
    if isinstance(exc, litellm.AuthenticationError):
        return f"The AI provider rejected the API key. {_NOTHING_WRITTEN} This needs fixing in the server configuration."
    if isinstance(exc, litellm.ContextWindowExceededError):
        return (
            "This conversation has grown too long for the model's context window. "
            f"{_NOTHING_WRITTEN} Please start a new chat."
        )
    if isinstance(exc, litellm.Timeout):
        return f"The AI provider did not respond in time. {_NOTHING_WRITTEN} {_TRY_AGAIN}"
    if isinstance(exc, litellm.ServiceUnavailableError) or _mentions(exc, "503", "unavailable", "overloaded"):
        return (
            f"The AI provider is overloaded (HTTP 503) and did not answer after several attempts. "
            f"{_NOTHING_WRITTEN} {_TRY_AGAIN}"
        )
    if isinstance(exc, litellm.InternalServerError) or _mentions(exc, "internalservererror", "500"):
        return (
            f"The AI provider reported an internal error (HTTP 500) and did not answer after several attempts. "
            f"{_NOTHING_WRITTEN} {_TRY_AGAIN}"
        )
    if isinstance(exc, litellm.APIConnectionError):
        return f"The AI provider could not be reached. {_NOTHING_WRITTEN} {_TRY_AGAIN}"
    if isinstance(exc, litellm.BadRequestError):
        return f"The AI provider rejected the request. {_NOTHING_WRITTEN} The details are in the server log."
    return f"The request to the AI provider failed. {_NOTHING_WRITTEN} The details are in the server log."


def _mentions(exc: BaseException, *needles: str) -> bool:
    """litellm often wraps the real cause in the message of a generic exception (a Gemini
    500 arrives as an APIConnectionError), so the text has to be consulted as well."""
    text = str(exc).lower()
    return any(needle in text for needle in needles)


__all__ = [
    "RETRY_STATUS",
    "FAILOVER_STATUS",
    "PARSE_FAILURE_MESSAGE",
    "GENERIC_FAILURE_MESSAGE",
    "describe_api_failure",
    "session_failure_detail",
    "short_reason",
]
