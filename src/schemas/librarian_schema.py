# src/schemas/librarian_schema.py
from pydantic import BaseModel, Field


class LibrarianInput(BaseModel):
    question: str = Field(description="The question to be answered from the vault contents.")
    ai_map: str = Field(description="Overview of all files and folders in the vault with short summaries, the starting point for research.")


class LibrarianOutput(BaseModel):
    answer: str = Field(description="The answer to the question, based on the vault content actually read.")
    sources: list[str] = Field(default_factory=list, description="Vault paths of the files the answer is based on.")


__all__ = [
    "LibrarianInput",
    "LibrarianOutput",
]
