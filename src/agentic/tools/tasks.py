# src/agentic/tools/tasks.py
"""WikiTool-Instanzen für Hintergrund-Aufgaben und Planungs-Management."""
from src.schemas.chat_schema import CheckTaskStatusArgs, StartBackgroundTaskArgs
from src.schemas.task_agent_schema import UpdatePlanArgs
from src.schemas.tool_schema import WikiTool
from src.agentic.engine.jobs import (
    check_task_status,
    start_background_task,
    _update_plan,
)

start_background_task_tool = WikiTool(
    name="start_background_task",
    description="Startet einen Task-Agenten, der eine mehrschrittige Aufgabe eigenständig im Hintergrund plant und abarbeitet. Blockiert nicht, gibt sofort eine task_id zurück.",
    parameters=StartBackgroundTaskArgs,
    func=start_background_task,
)

check_task_status_tool = WikiTool(
    name="check_task_status",
    description="Fragt Plan, Fortschritt und ggf. Endergebnis einer per start_background_task gestarteten Hintergrund-Aufgabe ab.",
    parameters=CheckTaskStatusArgs,
    func=check_task_status,
)

update_plan_tool = WikiTool(
    name="update_plan",
    description="Legt den vollständigen Arbeitsplan fest oder aktualisiert ihn (z.B. Status einzelner Schritte). Immer die komplette Liste aller Schritte übergeben.",
    parameters=UpdatePlanArgs,
    func=_update_plan,
)

__all__ = [
    "start_background_task_tool",
    "check_task_status_tool",
    "update_plan_tool",
]
