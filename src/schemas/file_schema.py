# src/schemas/file_schema.py
from typing import Any, Literal
from pydantic import BaseModel, Field


class FileNode(BaseModel):
    """Repräsentiert einen Knoten im Vault-Dateibaum (Datei oder Verzeichnis)."""
    name: str
    path: str
    type: Literal["file", "directory"]
    size: int | None = None
    last_modified: str | None = None
    ai_summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    linked_files: list[str] = Field(default_factory=list)
    children: list["FileNode"] | None = None


class FileTreeResponse(BaseModel):
    """Antwortmodell für den vollständigen Vault-Dateibaum."""
    root_path: str
    total_files: int
    total_directories: int
    items: list[FileNode]


class FileContentResponse(BaseModel):
    """Antwortmodell für den Inhalt einer einzelnen Datei."""
    path: str
    name: str
    raw_content: str
    body: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    ai_summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    linked_files: list[str] = Field(default_factory=list)
    last_modified: str | None = None


class RequestSummaryRequest(BaseModel):
    """Anfrage zum Anfordern/Neugenerieren einer KI-Zusammenfassung für eine Datei."""
    path: str


class RequestSummaryResponse(BaseModel):
    """Ergebnis nach der Neugenerierung der Zusammenfassung."""
    path: str
    success: bool
    ai_summary: str | None = None
    file: FileContentResponse | None = None
    message: str


class BuildMissingSummariesResponse(BaseModel):
    """Ergebnis nach dem Durchlauf zum Erstellen aller fehlenden Zusammenfassungen."""
    success: bool
    files_processed: int
    total_missing_files: int
    folders_processed: int
    errors: list[str] = Field(default_factory=list)
    message: str


class UpdateFileRequest(BaseModel):
    """Anfrage zum Bearbeiten/Speichern einer Datei im Vault."""
    path: str
    content: str


class UpdateFileResponse(BaseModel):
    """Antwort nach dem Bearbeiten einer Datei."""
    path: str
    success: bool
    message: str
    file: FileContentResponse | None = None


class DeleteFileResponse(BaseModel):
    """Antwort nach dem Löschen einer Datei."""
    path: str
    success: bool
    message: str

