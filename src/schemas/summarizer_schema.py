# src/schemas/summarizer_schema.py
from pydantic import BaseModel, Field


class SummarizerInput(BaseModel):
    current_content: str = Field(description="Current full text of the document.")
    previous_content: str = Field(default="", description="Previous full text of the document, if known.")
    prev_doc_summary: str = Field(default="", description="The existing summary of this document.")
    prev_filemap_summary: str = Field(default="", description="The existing short entry for this file in the central .ai_map.json.")


class SummarizerOutput(BaseModel):
    document_summary: str = Field(description="Concise summary (3-5 sentences) of the current document.")
    filemap_summary: str = Field(description="Very short one-sentence summary for the central file overview.")
