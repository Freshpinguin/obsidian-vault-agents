from typing import Any
from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    message: str = Field(min_length=1, description="The first message to the chat agent.")
    active_file: str | None = Field(default=None, description="Path of the note currently open in the editor.")
    active_file_summary: str | None = Field(default=None, description="Very short summary of the active note, from the ai_map.")


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, description="The next message to the chat agent.")
    active_file: str | None = Field(default=None, description="Path of the note currently open in the editor.")
    active_file_summary: str | None = Field(default=None, description="Very short summary of the active note, from the ai_map.")


class ChatReplyResponse(BaseModel):
    session_id: str
    reply: str
    mutations: list[dict[str, Any]] = Field(default_factory=list, description="List of vault mutations executed in this chat turn.")
