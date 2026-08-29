# src/schemas/reasoner_schema.py
from pydantic import BaseModel, Field


class ReasoningArgs(BaseModel):
    task: str = Field(
        description="Die Aufgabe für den Denk-Agenten: eine komplexe Überlegung oder ein auszuformulierender "
                     "Text, möglichst konkret und in sich verständlich formuliert (der Agent kennt den bisherigen "
                     "Chatverlauf nicht, nur das, was hier steht)."
    )
    file_paths: list[str] = Field(
        default_factory=list,
        description="Optionale Vault-Pfade, deren Inhalt als zusätzlicher Kontext mitgeschickt werden soll "
                     "(z.B. bestehende Lore-Dateien, auf denen die Ausarbeitung aufbauen soll).",
    )
