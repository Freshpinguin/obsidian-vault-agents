from typing import Any
from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    message: str = Field(min_length=1, description="Die erste Nachricht an den Chat-Agenten.")
    active_file: str | None = Field(default=None, description="Pfad der aktuell im Editor geöffneten Notiz.")
    active_file_summary: str | None = Field(default=None, description="Sehr kurze Zusammenfassung der aktiven Notiz aus der ai_map.")


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, description="Die nächste Nachricht an den Chat-Agenten.")
    active_file: str | None = Field(default=None, description="Pfad der aktuell im Editor geöffneten Notiz.")
    active_file_summary: str | None = Field(default=None, description="Sehr kurze Zusammenfassung der aktiven Notiz aus der ai_map.")


class ChatReplyResponse(BaseModel):
    session_id: str
    reply: str
    mutations: list[dict[str, Any]] = Field(default_factory=list, description="Liste von ausgeführten Vault-Mutationen in diesem Chat-Turn.")
