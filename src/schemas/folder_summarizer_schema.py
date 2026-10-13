# src/schemas/folder_summarizer_schema.py
from pydantic import BaseModel, Field


class FolderSummarizerInput(BaseModel):
    files_overview: str = Field(default="", description="Current file map of this folder: a list of the files with their respective summaries.")
    subfolder_summaries: str = Field(default="", description="Summaries of this folder's direct subfolders, if any.")
    prev_folder_summary: str = Field(default="", description="The existing, detailed summary of this folder from its .index.md.")
    prev_dirmap_summary: str = Field(default="", description="The existing short entry for this folder in the central .ai_map.json.")


class FolderSummarizerOutput(BaseModel):
    folder_summary: str = Field(description="Updated summary (4-5 sentences) for this folder's .index.md.")
    dirmap_summary: str = Field(description="Very short entry (a few words) for this folder in the central .ai_map.json.")
