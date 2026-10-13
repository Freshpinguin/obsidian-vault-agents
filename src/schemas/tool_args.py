# src/schemas/tool_args.py
"""Pydantic-Modelle für alle Werkzeug-Aufruf-Argumente."""
from typing import Literal
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    step: str = Field(description="Kurze Beschreibung dieses Arbeitsschritts.")
    status: Literal["pending", "in_progress", "done"] = Field(description="Aktueller Status dieses Schritts.")


class AskLibrarianArgs(BaseModel):
    question: str = Field(description="Die Recherche-Frage an den Librarian, der im Vault danach sucht.")


class CreateDirectoryArgs(BaseModel):
    path: str = Field(description="Vault-Pfad des neu anzulegenden Ordners (inkl. evtl. fehlender Zwischenordner).")


class CreateFileArgs(BaseModel):
    path: str = Field(description="Vault-Pfad der neu anzulegenden .md-Datei (muss noch nicht existieren).")
    content: str = Field(description="Inhalt der neuen Datei (reiner Markdown-Text, ohne Frontmatter).")


class EditFileArgs(BaseModel):
    path: str = Field(description="Vault-Pfad der zu bearbeitenden, bestehenden .md-Datei.")
    content: str = Field(description="Der NEUE vollständige Inhalt der Datei (ersetzt den bisherigen Inhalt unterhalb des Frontmatters komplett).")


class MoveFileArgs(BaseModel):
    path: str = Field(description="Vault-Pfad der zu verschiebenden/umzubenennenden bestehenden Datei.")
    new_path: str = Field(description="Neuer Vault-Pfad der Datei (muss noch nicht existieren, muss auf .md enden).")


class DeleteFileArgs(BaseModel):
    path: str = Field(description="Vault-Pfad der zu löschenden bestehenden .md-Datei.")


class StartBackgroundTaskArgs(BaseModel):
    description: str = Field(
        description="Vollständige, in sich verständliche Beschreibung der Aufgabe für den Task-Agenten "
                     "(der Task-Agent kennt den bisherigen Chatverlauf nicht, also relevanten Kontext mit hineinfassen)."
    )


class CheckTaskStatusArgs(BaseModel):
    task_id: str = Field(description="Die task_id, die start_background_task zurückgegeben hat.")


class PathsArgs(BaseModel):
    paths: list[str] = Field(
        description="Liste von Vault-Pfaden (Ordner oder Dateien). Immer alle relevanten Pfade auf einmal übergeben, "
                     "statt mehrere einzelne Aufrufe nacheinander zu machen."
    )


class UpdatePlanArgs(BaseModel):
    task_id: str = Field(description="Die eigene Task-ID.")
    steps: list[PlanStep] = Field(
        description="Der VOLLSTÄNDIGE aktuelle Plan (alle Schritte, nicht nur neue/geänderte), in "
                     "Abarbeitungsreihenfolge."
    )


class WebSearchArgs(BaseModel):
    query: str = Field(
        description="Die Frage oder das zu recherchierende Konzept, möglichst konkret und in sich "
                     "verständlich formuliert (wird per echter Google-Websuche beantwortet)."
    )


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


__all__ = [
    "PlanStep",
    "AskLibrarianArgs",
    "CreateDirectoryArgs",
    "CreateFileArgs",
    "EditFileArgs",
    "MoveFileArgs",
    "DeleteFileArgs",
    "StartBackgroundTaskArgs",
    "CheckTaskStatusArgs",
    "PathsArgs",
    "UpdatePlanArgs",
    "WebSearchArgs",
    "ReasoningArgs",
]
