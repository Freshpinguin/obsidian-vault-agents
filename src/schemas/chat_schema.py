# src/schemas/chat_schema.py
from pydantic import BaseModel, Field

from src.schemas.session_schema import (
    ChatMessageRequest,
    ChatReplyResponse,
    StartSessionRequest,
)
from src.schemas.tool_args import (
    AskLibrarianArgs,
    CheckTaskStatusArgs,
    CreateDirectoryArgs,
    CreateFileArgs,
    DeleteFileArgs,
    EditFileArgs,
    MoveFileArgs,
    StartBackgroundTaskArgs,
)


class ChatInput(BaseModel):
    message: str = Field(description="Die (erste) Nachricht des Nutzers im Chat.")


class ChatOutput(BaseModel):
    reply: str = Field(description="Die Antwort an den Nutzer im Chat, in normaler Konversationssprache.")


__all__ = [
    "ChatMessageRequest",
    "ChatReplyResponse",
    "StartSessionRequest",
    "ChatInput",
    "ChatOutput",
    "AskLibrarianArgs",
    "CreateDirectoryArgs",
    "CreateFileArgs",
    "EditFileArgs",
    "MoveFileArgs",
    "DeleteFileArgs",
    "StartBackgroundTaskArgs",
    "CheckTaskStatusArgs",
]
