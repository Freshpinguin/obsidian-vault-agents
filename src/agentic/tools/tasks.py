# src/agentic/tools/tasks.py
"""WikiTool instances for background tasks and plan management."""
from src.schemas.tool_args import (
    CheckTaskStatusArgs,
    StartBackgroundTaskArgs,
    UpdatePlanArgs,
)
from src.schemas.tool_schema import WikiTool
from src.agentic.engine.jobs import (
    check_task_status,
    start_background_task,
    _update_plan,
)

start_background_task_tool = WikiTool(
    name="start_background_task",
    description="Starts a task agent that plans and works through a multi-step assignment autonomously in the background. Does not block; returns a task_id immediately.",
    parameters=StartBackgroundTaskArgs,
    func=start_background_task,
)

check_task_status_tool = WikiTool(
    name="check_task_status",
    description="Queries the plan, progress and (if finished) final result of a background task started via start_background_task.",
    parameters=CheckTaskStatusArgs,
    func=check_task_status,
)

update_plan_tool = WikiTool(
    name="update_plan",
    description="Sets or updates the complete work plan (e.g. the status of individual steps). Always pass the complete list of all steps.",
    parameters=UpdatePlanArgs,
    func=_update_plan,
)

__all__ = [
    "start_background_task_tool",
    "check_task_status_tool",
    "update_plan_tool",
]
