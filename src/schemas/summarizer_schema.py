# src/schemas/summarizer_schema.py
from pydantic import BaseModel, Field


class SummarizerInput(BaseModel):
    current_content: str = Field(description="Aktueller Volltext des Dokuments.")
    previous_content: str = Field(default="", description="Vorheriger Volltext des Dokuments, falls bekannt.")
    prev_doc_summary: str = Field(default="", description="Bisherige Zusammenfassung dieses Dokuments.")
    prev_filemap_summary: str = Field(default="", description="Bisheriger Kurz-Eintrag dieser Datei in der zentralen .ai_map.json.")


class SummarizerOutput(BaseModel):
    document_summary: str = Field(description="Prägnante Zusammenfassung (3-5 Sätze) des aktuellen Dokuments.")
    filemap_summary: str = Field(description="Sehr kurze Ein-Satz-Zusammenfassung für die zentrale Dateiübersicht.")
