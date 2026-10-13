# src/schemas/chat_schema.py
from pydantic import BaseModel, Field


class ChatInput(BaseModel):
    message: str = Field(description="The user's (first) message in the chat.")


class ChatOutput(BaseModel):
    reply: str = Field(description="The reply to the user in the chat, in normal conversational language.")


__all__ = [
    "ChatInput",
    "ChatOutput",
]
