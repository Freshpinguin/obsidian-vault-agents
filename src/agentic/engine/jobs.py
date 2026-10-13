# src/agentic/engine/jobs.py
"""Background execution and job registry for asynchronous agent sessions."""
from dataclasses import dataclass, field
from datetime import datetime
import threading
from typing import TYPE_CHECKING, Any
import uuid

from src.core.logging_config import logger
from src.schemas.llm_models import LLMModels
from src.agentic.engine.model_rotation import task_rotation
from src.agentic.engine.runner import run_agent_session

if TYPE_CHECKING:
    from src.schemas.agent_schema import AgentSession


@dataclass
class TaskJob:
    task_id: str
    description: str
    status: str = "running"  # "running" | "done" | "error"
    plan: list[dict] = field(default_factory=list)
    session: Any | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None


_jobs: dict[str, TaskJob] = {}
_jobs_lock = threading.Lock()


def _format_plan(steps: list[dict]) -> str:
    if not steps:
        return "(no plan created yet)"
    markers = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}
    return "\n".join(f"{markers.get(s.get('status'), '[ ]')} {s.get('step', '')}" for s in steps)


def _update_plan(task_id: str, steps: list[dict]) -> str:
    with _jobs_lock:
        job = _jobs.get(task_id)
    if job is None:
        return f"Error: unknown task_id '{task_id}'."

    job.plan = steps
    logger.info(f"[TaskAgent] Plan for {task_id} updated ({len(steps)} steps).")
    return "Plan saved:\n" + _format_plan(steps)


def _run_job(job: TaskJob, model_override: LLMModels | None) -> None:
    # Deliberately local: breaks the cycle engine -> agents -> tools -> engine
    from src.agentic.agents.task_agent import TaskAgent, build_task_input

    try:
        input_data = build_task_input(job.task_id, job.description)
        session = run_agent_session(agent=TaskAgent, raw_input=input_data, model_override=model_override)
        job.session = session
        job.status = "done" if session.is_successful else "error"
        if not session.is_successful:
            job.error = "The task agent could not complete the assignment (iteration limit or repeatedly invalid response)."
    except Exception as e:
        logger.error(f"[TaskAgent] Background task {job.task_id} failed: {e}")
        job.status = "error"
        job.error = str(e)
    finally:
        job.finished_at = datetime.now()
        logger.info(f"[TaskAgent] Background task {job.task_id} finished: {job.status}")


def start_background_task(description: str, model_override: LLMModels | None = None) -> str:
    """Starts the task agent for an assignment in its own background thread and returns
    a confirmation with the task_id IMMEDIATELY (does not block). Progress can be
    queried via check_task_status(task_id). Without an explicit model_override, calls
    alternate between GEMINI_3_5_FLASH_LITE and GEMINI_3_1_FLASH_LITE to spread the
    free-tier tokens-per-minute limit across two models (the whole assignment then runs
    on the chosen model throughout; rotation applies per background task, not per
    round)."""
    job = TaskJob(task_id=uuid.uuid4().hex[:12], description=description)
    with _jobs_lock:
        _jobs[job.task_id] = job

    use_model = model_override or task_rotation.next()
    thread = threading.Thread(target=_run_job, args=(job, use_model), daemon=True)
    thread.start()

    logger.info(f"[TaskAgent] Background task {job.task_id} started: {description[:100]}")
    return (
        f"Background task started (task_id: {job.task_id}). "
        f"It keeps running in the background - query progress with check_task_status('{job.task_id}')."
    )


def check_task_status(task_id: str) -> str:
    """Returns the status, current plan and (once finished) the final report of an
    assignment started via start_background_task."""
    with _jobs_lock:
        job = _jobs.get(task_id)

    if job is None:
        return f"Error: no background task found with the ID '{task_id}'."

    lines = [
        f"Status: {job.status}",
        f"Task: {job.description}",
        "",
        "Plan:",
        _format_plan(job.plan),
    ]

    if job.status == "done" and job.session and job.session.is_successful:
        lines += ["", "Result:", job.session.final_result.summary]
    elif job.status == "error":
        lines += ["", f"Error: {job.error or 'Unknown error.'}"]

    return "\n".join(lines)


__all__ = [
    "TaskJob",
    "_jobs",
    "_jobs_lock",
    "_format_plan",
    "_update_plan",
    "start_background_task",
    "check_task_status",
]
