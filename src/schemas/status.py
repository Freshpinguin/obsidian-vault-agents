# src/schemas/enums.py
from enum import StrEnum

from pydantic import BaseModel

class AgentStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TOOL_CALL = "tool_call"

class ParseResult(BaseModel):
    """Encapsulates the result of parsing."""
    status: AgentStatus
    parsed_data: BaseModel | None = None
    error_report: str | None = None