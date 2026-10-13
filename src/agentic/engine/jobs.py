# src/agentic/engine/jobs.py
"""Hintergrund-Ausführung und Job-Registry für asynchrone Agenten-Sessions."""
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
        return "(noch kein Plan erstellt)"
    markers = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}
    return "\n".join(f"{markers.get(s.get('status'), '[ ]')} {s.get('step', '')}" for s in steps)


def _update_plan(task_id: str, steps: list[dict]) -> str:
    with _jobs_lock:
        job = _jobs.get(task_id)
    if job is None:
        return f"Fehler: Unbekannte task_id '{task_id}'."

    job.plan = steps
    logger.info(f"[TaskAgent] Plan für {task_id} aktualisiert ({len(steps)} Schritte).")
    return "Plan gespeichert:\n" + _format_plan(steps)


def _run_job(job: TaskJob, model_override: LLMModels | None) -> None:
    # bewusst lokal: bricht den Zyklus engine -> agents -> tools -> engine
    from src.agentic.agents.task_agent import TaskAgent, build_task_input

    try:
        input_data = build_task_input(job.task_id, job.description)
        session = run_agent_session(agent=TaskAgent, raw_input=input_data, model_override=model_override)
        job.session = session
        job.status = "done" if session.is_successful else "error"
        if not session.is_successful:
            job.error = "Der Task-Agent konnte die Aufgabe nicht abschließen (Iterationslimit oder wiederholt ungültige Antwort)."
    except Exception as e:
        logger.error(f"[TaskAgent] Hintergrund-Aufgabe {job.task_id} fehlgeschlagen: {e}")
        job.status = "error"
        job.error = str(e)
    finally:
        job.finished_at = datetime.now()
        logger.info(f"[TaskAgent] Hintergrund-Aufgabe {job.task_id} beendet: {job.status}")


def start_background_task(description: str, model_override: LLMModels | None = None) -> str:
    """Startet den Task-Agenten für eine Aufgabe in einem eigenen Hintergrund-Thread und
    gibt SOFORT eine Bestätigung mit task_id zurück (blockiert nicht). Der Fortschritt
    lässt sich über check_task_status(task_id) abfragen. Ohne explizites model_override
    wechselt jeder Aufruf abwechselnd zwischen GEMINI_3_5_FLASH_LITE und
    GEMINI_3_1_FLASH_LITE, um das Tokens/Minute-Limit der Free-Tier-API auf zwei
    Modelle zu verteilen (die gesamte Aufgabe läuft dann durchgängig mit dem gewählten
    Modell, die Rotation greift pro Hintergrund-Aufgabe, nicht pro Runde)."""
    job = TaskJob(task_id=uuid.uuid4().hex[:12], description=description)
    with _jobs_lock:
        _jobs[job.task_id] = job

    use_model = model_override or task_rotation.next()
    thread = threading.Thread(target=_run_job, args=(job, use_model), daemon=True)
    thread.start()

    logger.info(f"[TaskAgent] Hintergrund-Aufgabe {job.task_id} gestartet: {description[:100]}")
    return (
        f"Hintergrund-Aufgabe gestartet (task_id: {job.task_id}). "
        f"Läuft im Hintergrund weiter – Fortschritt mit check_task_status('{job.task_id}') abfragen."
    )


def check_task_status(task_id: str) -> str:
    """Gibt Status, aktuellen Plan und (falls fertig) den Abschlussbericht einer per
    start_background_task gestarteten Aufgabe zurück."""
    with _jobs_lock:
        job = _jobs.get(task_id)

    if job is None:
        return f"Fehler: Keine Hintergrund-Aufgabe mit der ID '{task_id}' gefunden."

    lines = [
        f"Status: {job.status}",
        f"Aufgabe: {job.description}",
        "",
        "Plan:",
        _format_plan(job.plan),
    ]

    if job.status == "done" and job.session and job.session.is_successful:
        lines += ["", "Ergebnis:", job.session.final_result.summary]
    elif job.status == "error":
        lines += ["", f"Fehler: {job.error or 'Unbekannter Fehler.'}"]

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
