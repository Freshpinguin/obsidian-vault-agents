# src/schemas/task_agent_schema.py
from pydantic import BaseModel, Field

from src.schemas.tool_args import PlanStep, UpdatePlanArgs


class TaskAgentInput(BaseModel):
    task_id: str = Field(description="Die eigene Task-ID – bei jedem update_plan-Aufruf als Referenz mitgeben.")
    task: str = Field(description="Die vollständige Aufgabenbeschreibung.")
    ai_map: str = Field(description="Übersicht aller Dateien und Ordner im Vault mit Kurz-Zusammenfassung, Ausgangspunkt für die Arbeit.")


class TaskAgentOutput(BaseModel):
    summary: str = Field(
        description="Abschlussbericht: was wurde konkret getan (inkl. tatsächlich verwendeter Vault-Pfade), "
                     "was ggf. nicht erledigt werden konnte und warum."
    )


__all__ = [
    "PlanStep",
    "TaskAgentInput",
    "TaskAgentOutput",
    "UpdatePlanArgs",
]
