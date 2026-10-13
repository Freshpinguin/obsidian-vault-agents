# src/schemas/file_schema.py
from typing import Any, Literal
from pydantic import BaseModel, Field


class FileNode(BaseModel):
    """Represents a node in the vault file tree (a file or a directory)."""
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
    """Response model for the complete vault file tree."""
    root_path: str
    total_files: int
    total_directories: int
    items: list[FileNode]


class FileContentResponse(BaseModel):
    """Response model for the content of a single file."""
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
    """Request to generate or regenerate an AI summary for a file."""
    path: str


class RequestSummaryResponse(BaseModel):
    """Result after regenerating the summary."""
    path: str
    success: bool
    ai_summary: str | None = None
    file: FileContentResponse | None = None
    message: str


class BuildMissingSummariesResponse(BaseModel):
    """Result after the pass that creates all missing summaries."""
    success: bool
    files_processed: int
    total_missing_files: int
    folders_processed: int
    errors: list[str] = Field(default_factory=list)
    message: str


class UpdateFileRequest(BaseModel):
    """Request to edit/save a file in the vault."""
    path: str
    content: str


class UpdateFileResponse(BaseModel):
    """Response after editing a file."""
    path: str
    success: bool
    message: str
    file: FileContentResponse | None = None


class DeleteFileResponse(BaseModel):
    """Response after deleting a file."""
    path: str
    success: bool
    message: str


class MoveNodeRequest(BaseModel):
    """Request to move a file or note within the vault."""
    path: str
    new_path: str


class CreateNoteRequest(BaseModel):
    """Request to create a new note file in the vault."""
    path: str
    content: str = ""


class MutationResponse(BaseModel):
    """Standard response model for file and folder write operations."""
    path: str
    success: bool
    message: str

