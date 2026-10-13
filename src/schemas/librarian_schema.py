# src/schemas/librarian_schema.py
from pydantic import BaseModel, Field

from src.schemas.tool_args import PathsArgs


class LibrarianInput(BaseModel):
    question: str = Field(description="Die Frage, die anhand des Vault-Inhalts beantwortet werden soll.")
    ai_map: str = Field(description="Übersicht aller Dateien und Ordner im Vault mit Kurz-Zusammenfassung, Ausgangspunkt für die Recherche.")


class LibrarianOutput(BaseModel):
    answer: str = Field(description="Die Antwort auf die Frage, gestützt auf den tatsächlich gelesenen Vault-Inhalt.")
    sources: list[str] = Field(default_factory=list, description="Vault-Pfade der Dateien, auf denen die Antwort beruht.")


__all__ = [
    "LibrarianInput",
    "LibrarianOutput",
    "PathsArgs",
]
