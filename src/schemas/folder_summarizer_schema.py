# src/schemas/folder_summarizer_schema.py
from pydantic import BaseModel, Field


class FolderSummarizerInput(BaseModel):
    files_overview: str = Field(default="", description="Aktuelle Datei-Map dieses Ordners: Liste der Dateien mit ihrer jeweiligen Zusammenfassung.")
    subfolder_summaries: str = Field(default="", description="Zusammenfassungen der direkten Unterordner dieses Ordners, falls vorhanden.")
    prev_folder_summary: str = Field(default="", description="Bisherige, ausführliche Zusammenfassung dieses Ordners aus dessen .index.md.")
    prev_dirmap_summary: str = Field(default="", description="Bisheriger Kurz-Eintrag dieses Ordners in der zentralen .ai_map.json.")


class FolderSummarizerOutput(BaseModel):
    folder_summary: str = Field(description="Aktualisierte Zusammenfassung (4-5 Sätze) für die .index.md dieses Ordners.")
    dirmap_summary: str = Field(description="Sehr kurzer Eintrag (wenige Wörter) für diesen Ordner in der zentralen .ai_map.json.")
