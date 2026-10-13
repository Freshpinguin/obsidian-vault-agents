# src/schemas/chat_schema.py
from pydantic import BaseModel, Field


class ChatInput(BaseModel):
    message: str = Field(description="Die (erste) Nachricht des Nutzers im Chat.")


class ChatOutput(BaseModel):
    reply: str = Field(description="Die Antwort an den Nutzer im Chat, in normaler Konversationssprache.")


__all__ = [
    "ChatInput",
    "ChatOutput",
]
