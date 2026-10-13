# src/agents/task_agent.py
"""Task-Agent: bearbeitet mehrschrittige Aufgaben eigenständig im Hintergrund – plant
zuerst (update_plan), arbeitet den Plan dann Schritt für Schritt ab (dieselben
Inhalts-/Änderungs-Werkzeuge wie der Chat-Agent, siehe shared_tools.py), mit deutlich
mehr ReAct-Runden als der Chat-Agent zur Verfügung stehen (der ist auf schnelle
Antworten optimiert, nicht auf lange autonome Abarbeitung).

Läuft über die normale run_agent_session-Maschinerie (litellm/WikiAgent/AgentSession),
aber IMMER in einem eigenen Hintergrund-Thread (siehe start_background_task), damit der
Chat-Agent, der ihn als Tool aufruft, nicht blockiert. Der Fortschritt (Plan + Status)
wird in der Job-Registry dieses Moduls gehalten, damit check_task_status ihn abfragen
kann, ohne selbst eine LLM-Session anzustoßen.
"""
import itertools
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from src.schemas.agent_schema import AgentSession, WikiAgent
from src.schemas.llm_models import LLMModels
from src.schemas.task_agent_schema import PlanStep, TaskAgentInput, TaskAgentOutput, UpdatePlanArgs
from src.schemas.tool_schema import WikiTool
from src.agentic.llm_engine import run_agent_session
from src.agentic.shared_tools import CONTENT_TOOLS
from src.core.logging_config import logger
from src.navigation import format_ai_map, load_ai_map

SYSTEM_PROMPT = """Du bist der Task-Agent eines persönlichen Obsidian-Wikis (Science-Fiction-Weltenbau).
Du bearbeitest eine einzelne, oft mehrschrittige Aufgabe komplett eigenständig im Hintergrund – es sitzt
NIEMAND im Gespräch, der Rückfragen beantworten kann. Triff bei Unklarheiten eine vernünftige, begründbare
Annahme und mach weiter, statt steckenzubleiben; nenne wichtige Annahmen und offene Punkte am Ende im Bericht.

Wichtig zur Mechanik, bevor es losgeht: Du hast bei jeder Antwort GENAU ZWEI Möglichkeiten, keine dritte.
(a) Einen oder mehrere Werkzeug-/Funktionsaufrufe (über den dafür vorgesehenen Function-Calling-Mechanismus
– nicht als Text beschrieben). Das ist dein Normalfall, solange die Aufgabe noch nicht fertig ist. (b) Die
finale JSON-Antwort mit "summary" – das ist NICHT die Standardantwort, sondern ausschließlich der ALLERLETZTE
Schritt, nachdem wirklich alle Planschritte erledigt sind (siehe unten). Verwechsle "die Aufgabe für mich
selbst zusammenfassen" nicht mit "die finale Antwort geben": Solange noch etwas zu tun ist, HANDELST du
(Werkzeugaufruf), du BERICHTEST nicht. Antworte niemals mit der finalen JSON-Struktur, nur weil du dir
vorstellen kannst, wie die Aufgabe gelöst würde – nur nachdem du sie durch tatsächliche Werkzeugaufrufe
wirklich gelöst hast.

Deine Arbeitsweise – erst planen, dann abarbeiten:

1. Rufe als ALLERERSTES update_plan(task_id, steps) auf und lege eine vollständige, konkrete Schrittliste für
   die Aufgabe an (jeder Schritt: kurze Beschreibung + Status "pending", der erste Schritt "in_progress").
   Zerlege dabei wirklich in einzelne, überprüfbare Arbeitsschritte statt einem einzigen groben Punkt.
2. Arbeite die Schritte der Reihe nach ab. Rufe update_plan erneut auf, sobald sich der Status ändert (Schritt
   abgeschlossen -> "done", nächster -> "in_progress") – IMMER mit der kompletten, aktuellen Schrittliste, nicht
   nur der Änderung. Falls sich während der Arbeit herausstellt, dass weitere Schritte nötig sind, ergänze sie.
3. Erst wenn alle Schritte "done" sind (oder du sicher bist, dass ein Schritt so nicht machbar ist), schreibe
   den Abschlussbericht.

Für die eigentliche Arbeit stehen dir dieselben Werkzeuge wie einem Chat-Assistenten dieses Wikis zur
Verfügung:

- load_files(paths): lädt den vollen Inhalt einer oder mehrerer Vault-Dateien direkt.
- ask_librarian(question): stellt dem Librarian-Agenten eine Recherche-Frage, wenn unklar ist, welche
  Datei(en) relevant sind – durchsucht den Vault eigenständig und liefert eine belegte Antwort inkl. Quellen
  (inkl. deren Volltext) zurück.
- web_search(query): recherchiert per echter Websuche im realen Internet (nicht im Vault) – für Realismus-/
  Faktenchecks von Universum-Konzepten oder allgemeine Fragen, die aktuelles Weltwissen brauchen.
- deep_reasoning(task, file_paths): für komplexe Überlegungen oder das Ausformulieren längerer, kohärenter
  Texte mit viel Kontext. file_paths werden automatisch als Kontext geladen – nicht vorher zusätzlich per
  load_files nachladen.
- create_directory(path): legt einen neuen Ordner an, inkl. fehlender Zwischenordner.
- create_file(path, content): legt eine neue .md-Datei mit Inhalt an.
- edit_file(path, content): ersetzt den Inhalt einer BESTEHENDEN Datei (Frontmatter bleibt erhalten). Nutze
  IMMER dieses Werkzeug, um eine vorhandene Datei zu ändern/ergänzen – NIEMALS move_file+create_file
  kombinieren (z.B. Original wegverschieben und neu anlegen), um das nachzubauen: das verdoppelt Aufrufe
  und lässt unnötig große Dateiinhalte doppelt im Kontext hängen.
- move_file(path, new_path): verschiebt/benennt eine bestehende Datei um (nur für echtes Verschieben/
  Umbenennen, nicht als Ersatz für edit_file).

Create_file/edit_file/move_file verweigern das Überschreiben bereits existierender Zielpfade (außer
edit_file, das ja gezielt Bestehendes ändert) und melden das als Fehler zurück – behandle das als normales
Ergebnis (z.B. anderen Pfad wählen oder im Bericht vermerken), nicht als Grund, die Aufgabe abzubrechen.
Nutze die Vault-Übersicht (ai_map), die du mit der Aufgabe bekommen hast, um dich zu orientieren, und die
Batch-Fähigkeit der Werkzeuge (mehrere Pfade/Aufrufe gleichzeitig), um mit möglichst wenigen Runden
auszukommen.

Erst NACHDEM die Aufgabe wirklich abgeschlossen ist (Plan komplett "done", per update_plan bestätigt) oder du
durch tatsächliche Versuche sicher bist, dass sie so nicht vollständig lösbar ist – nicht vorher, nicht als
Reflex auf die erste Anfrage – rufe kein Werkzeug mehr auf und antworte direkt im geforderten JSON-Format:

1. summary: Abschlussbericht – was wurde konkret getan (inkl. tatsächlich verwendeter Vault-Pfade), was
   ggf. nicht erledigt werden konnte und warum, welche Annahmen du getroffen hast.
"""


@dataclass
class TaskJob:
    task_id: str
    description: str
    status: str = "running"  # "running" | "done" | "error"
    plan: list[dict] = field(default_factory=list)
    session: AgentSession | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None


_jobs: dict[str, TaskJob] = {}
_jobs_lock = threading.Lock()

# Free-Tier-APIs begrenzen Tokens/Minute PRO Modell, und der Task-Agent kann durch
# seine vielen ReAct-Runden schnell in dieses Limit laufen. Abwechselnd zwischen zwei
# Modellen zu wechseln verteilt die Last auf zwei getrennte Kontingente (siehe
# librarian.py für dasselbe Muster). itertools.cycle + Lock, da mehrere Hintergrund-
# Aufgaben parallel in eigenen Threads gestartet werden können.
_MODEL_ROTATION = (LLMModels.GEMINI_3_5_FLASH_LITE, LLMModels.GEMINI_3_1_FLASH_LITE)
_rotation_lock = threading.Lock()
_rotation = itertools.cycle(_MODEL_ROTATION)


def _next_rotation_model() -> LLMModels:
    with _rotation_lock:
        return next(_rotation)


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


update_plan_tool = WikiTool(
    name="update_plan",
    description="Legt den vollständigen Arbeitsplan fest oder aktualisiert ihn (z.B. Status einzelner Schritte). Immer die komplette Liste aller Schritte übergeben.",
    parameters=UpdatePlanArgs,
    func=_update_plan,
)

TaskAgent = WikiAgent(
    name="TaskAgent",
    system_prompt=SYSTEM_PROMPT,
    input_type=TaskAgentInput,
    response_type=TaskAgentOutput,
    tools=[*CONTENT_TOOLS, update_plan_tool],
    max_tool_iterations=40,
    # Lange Sessions mit vielen ReAct-Runden lassen den Kontext sonst quadratisch
    # wachsen (jeder Tool-Aufruf/-Ergebnis bleibt für den Rest der Session im Kontext
    # hängen) - ein günstiges Modell verdichtet den älteren Verlauf bei Bedarf.
    enable_context_compaction=True,
    compaction_model=LLMModels.GEMMA_26B,
    compaction_threshold_chars=30000,
    compaction_keep_recent_rounds=3,
    # Verhindert das beobachtete Fehlerbild "Modell antwortet direkt mit einem
    # plausibel klingenden, aber komplett erfundenen Erfolgsbericht, ohne je
    # update_plan oder ein anderes Werkzeug aufgerufen zu haben".
    require_tool_call_first_round=True,
)


def _run_job(job: TaskJob, model_override: LLMModels | None) -> None:
    try:
        input_data = TaskAgentInput(
            task_id=job.task_id,
            task=job.description,
            ai_map=format_ai_map(load_ai_map()),
        )
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

    use_model = model_override or _next_rotation_model()
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
