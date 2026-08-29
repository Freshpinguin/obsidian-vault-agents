# src/schemas/task_agent_schema.py
from typing import Literal

from pydantic import BaseModel, Field


class TaskAgentInput(BaseModel):
    task_id: str = Field(description="Die eigene Task-ID – bei jedem update_plan-Aufruf als Referenz mitgeben.")
    task: str = Field(description="Die vollständige Aufgabenbeschreibung.")
    ai_map: str = Field(description="Übersicht aller Dateien und Ordner im Vault mit Kurz-Zusammenfassung, Ausgangspunkt für die Arbeit.")


class TaskAgentOutput(BaseModel):
    summary: str = Field(
        description="Abschlussbericht: was wurde konkret getan (inkl. tatsächlich verwendeter Vault-Pfade), "
                     "was ggf. nicht erledigt werden konnte und warum."
    )


class PlanStep(BaseModel):
    step: str = Field(description="Kurze Beschreibung dieses Arbeitsschritts.")
    status: Literal["pending", "in_progress", "done"] = Field(description="Aktueller Status dieses Schritts.")


class UpdatePlanArgs(BaseModel):
    task_id: str = Field(description="Die eigene Task-ID.")
    steps: list[PlanStep] = Field(
        description="Der VOLLSTÄNDIGE aktuelle Plan (alle Schritte, nicht nur neue/geänderte), in "
                     "Abarbeitungsreihenfolge."
    )
