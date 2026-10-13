# src/agentic/tools/tasks.py
"""WikiTool-Instanzen für Hintergrund-Aufgaben und Planungs-Management."""
from src.schemas.chat_schema import CheckTaskStatusArgs, StartBackgroundTaskArgs
from src.schemas.task_agent_schema import UpdatePlanArgs
from src.schemas.tool_schema import WikiTool


def _start_background_task_call(description: str) -> str:
    from src.agentic.agents.task_agent import start_background_task
    return start_background_task(description)


def _check_task_status_call(task_id: str) -> str:
    from src.agentic.agents.task_agent import check_task_status
    return check_task_status(task_id)


def _update_plan_call(task_id: str, steps: list[dict]) -> str:
    from src.agentic.agents.task_agent import _update_plan
    return _update_plan(task_id, steps)


start_background_task_tool = WikiTool(
    name="start_background_task",
    description="Startet einen Task-Agenten, der eine mehrschrittige Aufgabe eigenständig im Hintergrund plant und abarbeitet. Blockiert nicht, gibt sofort eine task_id zurück.",
    parameters=StartBackgroundTaskArgs,
    func=_start_background_task_call,
)

check_task_status_tool = WikiTool(
    name="check_task_status",
    description="Fragt Plan, Fortschritt und ggf. Endergebnis einer per start_background_task gestarteten Hintergrund-Aufgabe ab.",
    parameters=CheckTaskStatusArgs,
    func=_check_task_status_call,
)

update_plan_tool = WikiTool(
    name="update_plan",
    description="Legt den vollständigen Arbeitsplan fest oder aktualisiert ihn (z.B. Status einzelner Schritte). Immer die komplette Liste aller Schritte übergeben.",
    parameters=UpdatePlanArgs,
    func=_update_plan_call,
)

__all__ = [
    "start_background_task_tool",
    "check_task_status_tool",
    "update_plan_tool",
]
