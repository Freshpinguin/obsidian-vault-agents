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

from src.schemas.agent_schema import AgentSession, WikiAgent
from src.schemas.llm_models import LLMModels
from src.schemas.task_agent_schema import TaskAgentInput, TaskAgentOutput
from src.agentic.engine import run_agent_session
from src.agentic.engine.jobs import (
    TaskJob,
    _jobs,
    _jobs_lock,
    _format_plan,
    _update_plan,
    check_task_status,
    start_background_task,
)
from src.agentic.tools import CONTENT_TOOLS
from src.agentic.tools.tasks import update_plan_tool
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




def build_task_input(task_id: str, description: str) -> TaskAgentInput:
    """Erstellt das Eingabe-Objekt für den Task-Agenten."""
    return TaskAgentInput(
        task_id=task_id,
        task=description,
        ai_map=format_ai_map(load_ai_map()),
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
