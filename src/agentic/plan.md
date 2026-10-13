# Refactoring-Plan: Trennung von Agenten, Werkzeugen und Laufzeit

Status: Vorschlag, noch nicht umgesetzt.

Ziel: `src/agents/` enthält heute vier verschiedene Arten von Code in einer flachen
Ebene. Dieser Plan benennt das Paket in **`src/agentic/`** um und trennt den Inhalt
dort in drei Unterpakete — `agents/` (was ein Agent ist), `tools/` (was Agenten
aufrufen können) und `engine/` (der Code, der Agenten ausführt). Das vierte,
nicht-agentische Stück (`map_maintenance.py`) wandert nach `src/core/`, wo es hingehört.

---

## 1. Befund: was heute in `src/agents/` liegt

| Datei | Was wirklich drinsteckt | Gehört eigentlich zu |
|---|---|---|
| `llm_engine.py` (294) | ReAct-Schleife `_run_turn`, Session-Einstiegspunkte, JSON-Fence-Strip, zwei Halluzinations-Heuristiken | **engine/** |
| `context_compactor.py` (128) | Verdichtung des Verlaufs, wird nur von `_run_turn` aufgerufen | **engine/** |
| `chat.py` (235) | Prompt + `ChatAgent` + 2 Tool-Definitionen + 2 Einstiegsfunktionen + `format_message_with_active_file` | agents/ **und** tools/ |
| `task_agent.py` (234) | Prompt + `TaskAgent` + `update_plan`-Tool + Job-Registry (`_jobs`) + Thread-Start + Modell-Rotation | agents/ **und** tools/ **und** engine/ |
| `librarian.py` (124) | Prompt + `LibrarianAgent` + 3 Lade-Tools + Modell-Rotation | agents/ **und** tools/ |
| `shared_tools.py` (103) | 9 `WikiTool`-Instanzen + `CONTENT_TOOLS` | **tools/** |
| `summarizer.py` (47) | Prompt + `SummarizerAgent` | agents/ (sauber) |
| `folder_summarizer.py` (40) | Prompt + `FolderSummarizerAgent` | agents/ (sauber) |
| `web_search.py` (94) | Einzel-Aufruf via `google.genai`, kein `WikiAgent` | agents/ (Sonderform) |
| `reasoner.py` (83) | Einzel-Aufruf via `google.antigravity`, kein `WikiAgent` | agents/ (Sonderform) |
| `map_maintenance.py` (77) | Aufräumen der `.ai_map.json`, kein LLM-Aufruf, kein Agent | **`src/core/`** |

Konkrete Symptome dieser Vermischung:

- `src/agents/__init__.py` exportiert ausschließlich **Engine**-Funktionen
  (`run_agent_session`, `start_chat_session`, `continue_chat_session`) — das Agenten-Paket
  ist nach außen also faktisch die Engine-API.
- `shared_tools.py` existiert laut eigenem Docstring nur, um einen Zirkelimport zwischen
  `chat.py` und `task_agent.py` zu vermeiden. Der Name beschreibt nicht den Inhalt,
  sondern die Notlösung.
- Werkzeug-Definitionen sind über vier Dateien verstreut: `shared_tools.py` (9),
  `librarian.py` (3), `chat.py` (2), `task_agent.py` (1).
- Die Argument-Modelle der Vault-Schreibwerkzeuge (`CreateFileArgs`, `EditFileArgs`,
  `MoveFileArgs`, `DeleteFileArgs`, `CreateDirectoryArgs`, `AskLibrarianArgs`) liegen in
  `src/schemas/chat_schema.py`, obwohl sie nichts mit dem Chat zu tun haben — der Task-Agent
  nutzt dieselben Werkzeuge.
- Die Modell-Rotation (`itertools.cycle` + `Lock` + `_next_rotation_model`) steht zweimal
  wortgleich in `librarian.py` und `task_agent.py`; der Kommentar in `task_agent.py`
  verweist dafür explizit auf `librarian.py`.
- `map_maintenance.py` importiert nur aus `src/core/` und wird nur von `src/main.py`
  gestartet — es hat keinen Bezug zum Agenten-Paket.

Positiv und zu erhalten: `src/core/`, `src/routes/`, `src/navigation/` sind bereits
sauber getrennt, und `src/tests/` spiegelt mit `tests/engine/` vs. `tests/agents/`
die hier vorgeschlagene Trennung schon ansatzweise.

---

## 2. Zielstruktur

Das Paket wird zu `src/agentic/`; die drei Zuständigkeiten werden Unterpakete:

```
src/agentic/
  __init__.py                 # nur Docstring, keine Fassade (siehe 2.3)

  agents/                     # WAS ein Agent ist: Prompt + WikiAgent + Einstiegsfunktion
    __init__.py               #   Agenten-Registry (Name -> WikiAgent)
    chat.py
    task_agent.py
    librarian.py
    summarizer.py
    folder_summarizer.py
    reasoner.py               #   Sonderform: direkter SDK-Aufruf, kein WikiAgent
    web_search.py             #   Sonderform: direkter SDK-Aufruf, kein WikiAgent

  tools/                      # WAS Agenten aufrufen können: alle WikiTool-Instanzen
    __init__.py               #   CONTENT_TOOLS + benannte Tool-Sets
    vault_read.py             #   load_files, load_file_summaries, load_directory_summaries
    vault_write.py            #   create_directory, create_file, edit_file, move_file, delete_file
    delegation.py             #   ask_librarian, web_search, deep_reasoning (Agenten als Werkzeug)
    tasks.py                  #   start_background_task, check_task_status, update_plan

  engine/                     # WIE Agenten laufen: kennt keinen einzelnen Agenten
    __init__.py               #   öffentliche API: run_agent_session, start/continue_chat_session
    runner.py                 #   _run_turn + die drei Session-Einstiegspunkte  (aus llm_engine.py)
    compaction.py             #   maybe_compact, context_size_chars             (aus context_compactor.py)
    response.py               #   strip_json_fence + Antwort-Validierung        (aus llm_engine.py)
    guards.py                 #   skipped_required_tool / hallucinated_mutation (aus llm_engine.py)
    model_rotation.py         #   ModelRotation-Helfer (entdoppelt)
    jobs.py                   #   TaskJob + _jobs-Registry + Thread-Start       (aus task_agent.py)

src/core/map_maintenance.py   # verschoben, sonst unverändert
src/core/  navigation/  schemas/  routes/   # unverändert
```

### 2.1 Die Leitregel

An ihr lässt sich jede Datei prüfen, und sie gilt innerhalb von `src/agentic/` genauso,
wie sie zwischen Top-Level-Paketen gegolten hätte:

- **`agents/`** darf aus `engine/`, `tools/` und `src/schemas/` importieren.
- **`tools/`** darf aus `engine/`, `src/navigation/`, `src/core/` und `src/schemas/`
  importieren — aus `agents/` nur verzögert (siehe Abschnitt 4).
- **`engine/`** darf aus `src/schemas/` und `src/core/logging_config` importieren,
  **nie** aus `agents/` oder `tools/`. Sie bekommt Agenten als Parameter übergeben,
  nicht per Import.

Die Abhängigkeiten zeigen also in eine Richtung: `agents -> tools -> engine`.

### 2.2 Warum das Oberpaket umbenannt wird

Behielte das Oberpaket den Namen `agents`, hieße das Unterpaket mit den Agenten
`src/agents/agents/` — beim Import unlesbar (`from src.agents.agents.chat import ...`)
und ohne jeden Informationsgewinn durch die Dopplung. Ein Ersatzname für das
Unterpaket (`definitions/`, `roster/`, `profiles/`) würde das Problem umgehen, aber
den Preis an der falschen Stelle zahlen: Die Agenten-Dateien sind der Kern des Pakets
und sollten den naheliegendsten Namen tragen.

Also wird das Oberpaket umbenannt: `src/agentic/` beschreibt die Schicht als Ganzes —
alles, was mit LLM-Agenten zu tun hat —, und `agents/` darin heißt dann genau das, was
drinsteht. Nebeneffekt: Die Top-Level-Pakete lesen sich danach als klare Arbeitsteilung
(`src/core/` Vault-Verwaltung, `src/agentic/` KI-Schicht, `src/navigation/` Vault-Zugriff,
`src/routes/` HTTP, `src/schemas/` Datenmodelle) statt dass ein Paketname gleichzeitig
die Schicht und einen ihrer Teile bezeichnet.

Die Umbenennung ist **nur in Schritt 2 praktisch kostenlos**: Dieser Schritt schreibt
ohnehin jede `src.agents...`-Importzeile im Projekt neu. Wird sie später nachgeholt,
ist dieselbe Arbeit ein zweites Mal zu machen — inklusive der Test-Patch-Strings aus
Abschnitt 6. Wenn `agentic` nicht gefällt, sind `src/ai/` (kürzer) oder `src/agency/`
gleichwertige Kandidaten; die Entscheidung muss nur vor Schritt 2 fallen.

### 2.3 `src/agentic/__init__.py` als Fassade

Heute ist es faktisch die Engine-API, und zwar zufällig: Es exportiert drei
Engine-Funktionen, weil die mal gebraucht wurden. Künftig ist es eine **bewusste
Fassade** — die eine Stelle, die festhält, was die Schicht nach außen anbietet:

```python
# src/agentic/__init__.py
from src.agentic.agents.chat import continue_wiki_chat, start_wiki_chat
from src.agentic.agents.folder_summarizer import FolderSummarizerAgent
from src.agentic.agents.summarizer import SummarizerAgent
from src.agentic.engine import run_agent_session

__all__ = ["start_wiki_chat", "continue_wiki_chat", "run_agent_session",
           "SummarizerAgent", "FolderSummarizerAgent"]
```

Fünf Namen, zwei Nutzer (siehe die Tabelle in 9.1) — mehr braucht niemand von außen.
Der Gewinn ist nicht Bequemlichkeit, sondern **Durchsetzbarkeit**: Der ast-Scan-Test aus
Abschnitt 6 kann dann eine einzige Regel prüfen — *außerhalb von `src/agentic/` darf
niemand `src.agentic.<unterpaket>` importieren, nur `src.agentic`* — und die
Fünf-Namen-Schnittstelle ist damit eine Tatsache statt einer Absichtserklärung. Nebenbei
berührt internes Umsortieren danach `src/routes/` nicht mehr.

Zwei Dinge, die dazugehören:

- **Genau ein gültiger Importweg.** Die Fassade ist nur dann eine Grenze, wenn der
  direkte Weg auf Unterpakete von außen verboten *und* getestet ist. Sonst sind es zwei
  Importwege, und das ist schlechter als keine Fassade. Tests dürfen weiter direkt in
  die Unterpakete greifen (sie testen Interna) — der Scan betrachtet nur
  Produktionscode.
- **Der verzögerte Import in `core/obsidian_processor.py` bleibt.** Die Fassade löst den
  Zyklus aus Abschnitt 4 nicht, sie verschärft ihn leicht: `core -> src.agentic` lädt den
  kompletten Agenten-Baum inklusive beider Google-SDKs, nur um an `run_agent_session` zu
  kommen. Gemessen auf dem Entwicklungsrechner: `src.agents.chat` importieren kostet
  3,8 s und 2994 Module, `llm_engine` allein 3,1 s und 2430 — die Differenz sind
  `google.antigravity` und `google.genai`, die `reasoner.py` und `web_search.py` auf
  Modulebene ziehen. Im laufenden Server ist das gleichgültig (FastAPI lädt beim Start
  ohnehin alles), deshalb hier kein Grund für Gegenmaßnahmen. Sollte die Testsuite
  dadurch merklich langsamer werden, macht ein `__getattr__` auf Modulebene (PEP 562)
  die Fassade in ~10 Zeilen lazy; bewusst nicht der Standardweg, weil es
  IDE-Autovervollständigung und Typprüfung verwirrt.

Der Kontrast zwischen den zwei Agenten-Bauarten gehört in den Docstring von
`agents/__init__.py`: fünf Agenten laufen über die Engine (multiturn, strukturierte
Antwort, Werkzeuge), zwei (`reasoner`, `web_search`) sind einmalige SDK-Aufrufe ohne
Session.

---

## 3. Datei-für-Datei-Zuordnung

### 3.1 `llm_engine.py` -> `engine/`

| Heute | Ziel |
|---|---|
| `_run_turn`, `FORCE_FINAL_ANSWER_INSTRUCTION` | `engine/runner.py` |
| `run_agent_session`, `start_chat_session`, `continue_chat_session` | `engine/runner.py`, re-exportiert in `engine/__init__.py` |
| `_strip_json_fence` | `engine/response.py` (als `strip_json_fence`, ohne Unterstrich — wird getestet) |
| Block "skipped_required_tool" (Zeile ~188) | `engine/guards.py: check_skipped_required_tool(agent, tool_steps)` |
| Block "hallucinated_mutation" (Zeilen ~192–210) | `engine/guards.py: check_hallucinated_mutation(agent, parse_result, tool_steps)` |

`_run_turn` ist mit ~220 Zeilen und drei verschachtelten Zuständen (`tool_steps`,
`parse_attempts`, `force_final_answer`) die komplexeste Funktion im Projekt. Das Herausziehen
der beiden Heuristiken nach `guards.py` ist der größte Lesbarkeitsgewinn des ganzen
Refactorings: Die Stichwortliste (`MUTATION_INDICATORS`, `NEGATIONS`) ist Fachlogik und
keine Schleifenmechanik, und `guards.py` lässt sich isoliert und tabellarisch testen.

`mutation_tool_names` dort ist außerdem eine hartkodierte Dopplung der Werkzeugnamen aus
`vault_write.py`. Achtung: `guards.py` darf die Namen nach der Leitregel **nicht** aus
`tools/` importieren. Saubere Auflösung: die Namensmenge lebt in `src/schemas/` (z.B.
`tool_args.py` oder eine kleine Konstante in `schemas/tool_schema.py`), und sowohl
`tools/vault_write.py` als auch `engine/guards.py` beziehen sie von dort.

### 3.2 `task_agent.py` -> aufgeteilt

| Heute | Ziel |
|---|---|
| `SYSTEM_PROMPT`, `TaskAgent` | `agents/task_agent.py` |
| `TaskJob`, `_jobs`, `_jobs_lock`, `_run_job`, `start_background_task`, `check_task_status`, `_format_plan`, `_update_plan` | `engine/jobs.py` |
| `update_plan_tool`, Tool-Hüllen für start/check | `tools/tasks.py` |
| `_MODEL_ROTATION`, `_rotation_lock`, `_next_rotation_model` | `engine/model_rotation.py` (Mechanismus) + `agents/task_agent.py` (das Modell-Tupel) |

`engine/jobs.py` ist die Hintergrund-Ausführung *irgendeiner* Agenten-Session, nicht
speziell des Task-Agenten — deshalb engine und nicht agents. Beim Verschieben die
Abhängigkeit umdrehen: `_run_job` bekommt den auszuführenden Agenten und den Input-Builder
als Parameter, statt `TaskAgent` direkt zu importieren. Sonst entsteht ein Import
`engine/ -> agents/`, der die Leitregel bricht.

### 3.3 `librarian.py`, `chat.py`

| Heute | Ziel |
|---|---|
| `librarian.py`: `directory_summaries_tool`, `file_summaries_tool`, `files_tool`, `_adapt` | `tools/vault_read.py` |
| `librarian.py`: Prompt, `LibrarianAgent`, `ask_librarian` | `agents/librarian.py` |
| `librarian.py`: Modell-Rotation | `engine/model_rotation.py` |
| `chat.py`: `start_background_task_tool`, `check_task_status_tool` | `tools/tasks.py` |
| `chat.py`: Prompt, `ChatAgent`, `start_wiki_chat`, `continue_wiki_chat`, `format_message_with_active_file` | `agents/chat.py` |

`format_message_with_active_file` bleibt bewusst beim Chat-Agenten: Es formatiert eine
Nutzer-Nachricht fürs Chat-Frontend und betrifft keinen anderen Agenten.

### 3.4 `shared_tools.py` -> aufgelöst

Die Datei verschwindet, ihre neun Werkzeuge verteilen sich:

- `ask_librarian_tool`, `web_search_tool`, `reasoning_tool` -> `tools/delegation.py`
  (das sind die drei Werkzeuge, die wiederum Agenten starten)
- `create_directory_tool`, `create_file_tool`, `edit_file_tool`, `move_file_tool`,
  `delete_file_tool` -> `tools/vault_write.py`
- `CONTENT_TOOLS` -> `tools/__init__.py`

Damit entfällt der Grund für ihre Existenz: Sie war laut Docstring nur der Umweg um
einen Zirkelimport. `tools/` löst denselben Zweck strukturell statt als Sonderfall.

### 3.5 `map_maintenance.py` -> `src/core/`

Verschieben nach `src/core/map_maintenance.py`, Export in `src/core/__init__.py`
ergänzen, Import in `src/main.py:19` anpassen. Reines Umbenennen, keine
Code-Änderung — die Datei importiert heute schon ausschließlich aus `src/core/`.
Das ist der einzige Teil des Refactorings, der die Agenten-Schicht verlässt.

### 3.6 `web_search.py`, `reasoner.py`

Wandern nach `agents/`, weil sie konzeptionell Agenten sind (LLM-Aufruf mit eigenem
System-Prompt), auch wenn sie nicht über `WikiAgent`/`AgentSession` laufen. Ihre
`WikiTool`-Hüllen ziehen nach `tools/delegation.py` — dann ist die Trennung
"Fähigkeit" vs. "als Werkzeug angeboten" auch hier konsistent.

### 3.7 `src/schemas/`

Die Tool-Argument-Modelle aus `chat_schema.py` nach `src/schemas/tool_args.py` verschieben:
`AskLibrarianArgs`, `CreateDirectoryArgs`, `CreateFileArgs`, `EditFileArgs`, `MoveFileArgs`,
`DeleteFileArgs`, `StartBackgroundTaskArgs`, `CheckTaskStatusArgs`, dazu `PathsArgs`
(heute `librarian_schema.py`), `UpdatePlanArgs` (heute `task_agent_schema.py`) und
`WebSearchArgs`/`ReasoningArgs` (heute eigene Dateien). In `chat_schema.py` bleiben nur
`ChatInput`/`ChatOutput`.

`src/schemas/` bleibt absichtlich **außerhalb** von `src/agentic/`: Die Modelle werden
auch von `src/routes/` und `src/core/` genutzt, sie sind kein Agenten-Detail.

Teilweise optional — aber die Namensmenge der Mutations-Werkzeuge aus 3.1 braucht einen
agentenneutralen Ort, also mindestens diesen einen Teil mitnehmen.

---

## 4. Das eine echte Problem: Zirkelimport bei den Task-Werkzeugen

Alles andere ist Verschieben. Diese Stelle braucht eine Entscheidung — und sie bleibt
auch in der verschachtelten Struktur bestehen, weil Python-Zyklen nicht davon abhängen,
ob Module Geschwister oder Nachbarpakete sind:

```
agents/chat.py             -> braucht tools/tasks.py            (start_background_task als Werkzeug)
tools/tasks.py             -> braucht engine/jobs.py            (den Thread-Start)
engine/jobs.py             -> braucht agents/task_agent.py      (den auszuführenden Agenten)  <-- Zyklus
agents/task_agent.py       -> braucht tools/__init__.py         (CONTENT_TOOLS)                <-- Zyklus
```

Heute existiert der Zyklus nicht, weil `task_agent.py` sowohl Agent als auch Job-Registry
ist und `shared_tools.py` als zyklusfreie Zwischenschicht dient. Nach dem Aufteilen
muss er explizit gebrochen werden.

**Entschieden: Option (A), verzögerter Import.** Die Optionen (B) und (C) sind unten nur
zur Nachvollziehbarkeit dokumentiert — nicht umsetzen, nicht neu aufrollen.

### (A) Verzögerter Import in der Job-Funktion — so wird es gemacht

`engine/jobs.py` importiert den Agenten erst im Funktionskörper:

```python
def start_background_task(description: str, model_override=None) -> str:
    # bewusst lokal: bricht den Zyklus engine -> agents -> tools -> engine
    from src.agentic.agents.task_agent import TaskAgent, build_task_input
    ...
```

Eine Zeile, ein in Python übliches Idiom, und `src/core/obsidian_processor.py:282` nutzt
dasselbe Muster bereits für dieselbe Art Abhängigkeit. Das Modul ist zum Aufrufzeitpunkt
vollständig geladen, der Import ist danach gecacht und kostet nichts, und er ist
thread-sicher — wichtig, weil `start_background_task` von mehreren Chat-Sessions parallel
aufgerufen werden kann.

Zwei Dinge sind Bedingung dafür, dass das so bleibt:

1. **Der Kommentar bleibt an der Importzeile.** Der einzige reale Fehlerfall ist nicht die
   Laufzeit, sondern ein späteres Aufräumen: Zieht jemand (oder ein Agent) die Zeile an den
   Dateikopf, gibt es einen `ImportError` beim Start, dessen Traceback auf das falsche Modul
   zeigt. Der Kommentar ist das, was das verhindert.
2. **Der ast-Scan-Test aus Abschnitt 6** fängt genau dieses Hochziehen mechanisch ab, mit
   dem verzögerten Import als dort dokumentierter Ausnahme.

Bewusst in Kauf genommen: Ein Tippfehler im verzögerten Importpfad fällt erst beim *Aufruf*
auf, nicht beim Start. Hier ist das abgedeckt, weil `tests/test_infrastructure.py:8` und die
Task-Agent-Tests tatsächlich eine Hintergrund-Aufgabe starten und den Import damit bei jedem
Testlauf ausführen.

### (B) Injektion statt Import — verworfen
`engine/jobs.py` bekommt Agent und Input-Builder als Parameter;
`agents/task_agent.py` exportiert eine dünne `start_background_task(description)`,
die beides einsetzt, und `tools/tasks.py` bindet diese Funktion. Dann zeigt kein Import
von `engine/` nach `agents/` — architektonisch die saubere Variante, kostet aber eine
zusätzliche Indirektionsebene und bricht den zweiten Zyklus
(`agents/task_agent -> tools`) noch nicht.

### (C) Tool-Verdrahtung in einer eigenen Registry — verworfen
Agenten deklarieren nur Tool-*Namen*, `agents/__init__.py` baut die `WikiAgent`-
Instanzen und setzt die Werkzeuge ein. Löst beide Zyklen vollständig, ist aber für
sieben Agenten deutlich überdimensioniert und macht `ChatAgent` nicht mehr als
Konstante importierbar — was die Tests heute tun.

Ergebnis: `tools/tasks.py` importiert nur aus `engine/jobs.py`, nie aus `agents/`. Damit
bleibt die Leitregel aus 2.1 auf Modul-Ebene eingehalten und der Zyklus existiert nur zur
Laufzeit an genau einer, kommentierten Stelle.

---

## 5. Reihenfolge der Umsetzung

Jeder Schritt ist einzeln commit- und testbar (`pytest` nach jedem Schritt; 20 Testdateien
decken Engine, Agenten und Routen ab).

1. **`map_maintenance.py` nach `src/core/`.** Reines Verschieben, ein Import in
   `src/main.py` zu ändern. Verkleinert das Problem, bevor es kompliziert wird.

2. **`src/agents/` nach `src/agentic/` umbenennen und `src/agentic/agents/` anlegen**,
   dann alle sieben Agenten-Dateien unverändert
   eine Ebene tiefer schieben (`chat.py`, `task_agent.py`, `librarian.py`,
   `summarizer.py`, `folder_summarizer.py`, `reasoner.py`, `web_search.py`).
   `llm_engine.py`, `context_compactor.py` und `shared_tools.py` bleiben vorerst oben
   liegen und wandern in Schritt 3 bzw. 5.
   Das ist der Commit mit den meisten berührten Importeuren, aber ohne eine Zeile
   Logikänderung: `src/routes/session/post_session.py:2`,
   `src/routes/session/post_message.py:2`, `src/core/obsidian_processor.py:283,316`
   sowie rund zehn Testdateien und die Patch-Strings in `tests/conftest.py`
   (Zeilen 75–76, 105, 114, 137, 142) und `tests/fakes/` (siehe Abschnitt 6).
   Beide Umbenennungen gehören in **einen** Commit: Sie schreiben dieselben Importzeilen
   um, und getrennt wäre die Arbeit doppelt (2.2). Den Paketnamen vorher festlegen —
   eine spätere Umbenennung heißt, diesen Schritt zweimal zu machen.

3. **`src/agentic/engine/` anlegen**, `llm_engine.py` -> `engine/runner.py` und
   `context_compactor.py` -> `engine/compaction.py` verschieben, Re-Exports in
   `engine/__init__.py`. Nur Importpfade ändern, kein Code anfassen.
   Betroffen: die drei Agenten in `agents/`, `core/obsidian_processor.py:282,315`,
   `tests/engine/test_run_turn.py`, `tests/unit/test_strip_json_fence.py`,
   `tests/agents/test_context_compactor.py`, `tests/conftest.py:95`.

4. **`engine/response.py` + `engine/guards.py` herausziehen.** Erste echte
   Code-Änderung; `_run_turn` schrumpft dabei um etwa ein Drittel. Die Heuristiken
   werden dadurch direkt testbar — neue Tests in `tests/engine/test_guards.py`.
   Hier zugleich die Werkzeugnamen-Konstante aus 3.1 an ihren neutralen Ort legen.
   Ebenfalls hier: **`SessionLogger` aus `src/core/logging_config.py` nach
   `engine/session_log.py` ziehen** (Begründung in 9.2). Produktiv nutzt ihn genau eine
   Datei (`llm_engine.py:62`), dazu `tests/agents/test_context_compactor.py` und
   `tests/agents/test_agent_registry.py:19`; `src/core/__init__.py:2,18` exportiert ihn
   und muss mitgezogen werden.

5. **`src/agentic/tools/` anlegen**, `shared_tools.py` auflösen, Lade-Tools aus
   `agents/librarian.py` und Task-Tools aus `agents/chat.py` /
   `agents/task_agent.py` dorthin ziehen. `CONTENT_TOOLS` bleibt namensgleich,
   damit `tests/agents/test_task_agent.py:14` nur den Importpfad wechseln muss.

6. **`engine/jobs.py` herausziehen** (Job-Registry aus `agents/task_agent.py`) mit
   dem verzögerten Import aus Abschnitt 4. Hier sind Tests anzupassen:
   `tests/test_infrastructure.py:8` und `tests/agents/test_agent_registry.py:7`
   greifen auf `task_agent._jobs` zu, `tests/conftest.py:137` patcht
   heute `src.agents.task_agent.threading.Thread` — dieser Patch zielt danach auf
   `src.agentic.engine.jobs.threading.Thread`.

7. **`engine/model_rotation.py`** — die doppelte Rotation entdoppeln. Achtung:
   `tests/agents/test_agent_registry.py:7-8` importieren `_MODEL_ROTATION` aus beiden
   Modulen; die Modell-Tupel bleiben pro Agent definiert, nur der Mechanismus wird geteilt.

8. **Fassade anlegen und die Grenze testbar machen.** Erst jetzt, weil die endgültige
   Struktur dafür stehen muss:
   - `src/agentic/__init__.py` auf die Fünf-Namen-Fassade aus 2.3 bringen.
   - Die beiden Nutzer darauf umstellen: `routes/session/post_session.py`,
     `routes/session/post_message.py` auf `from src.agentic import ...`; die
     verzögerten Importe in `core/obsidian_processor.py:282,315` ebenfalls auf die
     Fassade (verzögert bleiben sie, siehe 2.3).
   - Den ast-Scan-Test mit seinen drei Zusicherungen schreiben (Abschnitt 6),
     z.B. als `tests/unit/test_import_boundaries.py`.
   Dieser Schritt ist der, der aus der neuen Ordnerstruktur eine durchgesetzte Grenze
   macht — ohne ihn ist die Aufteilung nur eine Konvention.

9. **Optional: `src/schemas/tool_args.py`** (Abschnitt 3.7).

10. **README-Architekturdiagramm und die Docstrings von `src/agentic/__init__.py`
    und `agents/__init__.py` schreiben** (2.2, 2.3). Das Diagramm im README beschreibt
    den Datenfluss und bleibt gültig; ergänzen lässt sich die Paket-Aufteilung als
    kurze Liste.

Schritte 1, 2, 3, 5 sind mechanisch; 4, 6, 7, 8 ändern Code und brauchen den Testlauf.
Nach Schritt 6 ist die Struktur fertig, nach Schritt 8 ist sie gesichert — 9 und 10
sind Aufräumen.

---

## 6. Was dabei zu beachten ist

**Der Introspektions-Test muss umgestellt werden.**
`tests/agents/test_agent_registry.py:23` läuft mit `pkgutil.iter_modules(agents_pkg.__path__)`
über `src.agents` und prüft, dass genau `{Chat, TaskAgent, Librarian, Summarizer,
FolderSummarizer}` gefunden werden. `iter_modules` steigt **nicht** in Unterpakete ab —
nach Schritt 2 findet er also nichts mehr und der Test wird grün-falsch bzw. schlägt mit
leerer Menge fehl. Umstellen auf `src.agentic.agents` als Wurzel (nicht auf
`walk_packages` über `src.agentic`, sonst sammelt er auch Tool- und Engine-Module ein).
Danach ist der Test sogar *stärker*, weil `agents/` nichts anderes mehr enthält.

Lohnend als Ergänzung: **ein** ast-Scan-Test über die Importe des Produktionscodes, der
drei Dinge zusichert:

1. Kein Modul unter `src/agentic/engine/` importiert aus `src.agentic.agents` oder
   `src.agentic.tools` (Leitregel 2.1). Der verzögerte Import aus Abschnitt 4 steht
   bewusst als dokumentierte Ausnahme drin.
2. Kein Modul außerhalb von `src/agentic/` importiert `src.agentic.<unterpaket>` —
   von außen gilt nur die Fassade `src.agentic` (2.3). Testcode ist ausgenommen.
3. Jedes Paket importiert nur aus den Paketen, die ihm laut Schichtung in 9.2 erlaubt
   sind (Positivliste statt Einzelverbote).

Punkt 3 macht aus der Architektur eine ausführbare Zusicherung — eine verletzte Grenze
fällt im Testlauf auf und nicht drei Monate später.

**`conftest.py` patcht nach Modulpfad.**
Die Fixtures setzen `monkeypatch.setattr("src.agents.llm_engine.supports_tool_choice", ...)`,
`"src.agents.web_search._get_client"`, `"src.agents.reasoner.Agent"` und
`"src.agents.task_agent.threading.Thread"`. Diese Strings sind Textreferenzen, die kein
Linter findet und die bei einem Tippfehler stumm ins Leere patchen (echte API-Aufrufe im
Testlauf). Bei jedem Schritt mitziehen und danach gezielt prüfen, dass die betroffenen
Tests ohne Netz laufen. Gleiches gilt für `tests/fakes/fake_genai.py:6` und
`tests/fakes/fake_antigravity.py:12`.

**`fake_llm.py` erkennt Agenten am Prompt.**
`tests/fakes/fake_llm.py:154-159` importiert die Agenten lazy und ordnet LLM-Aufrufe über
`COMPACTION_SYSTEM_PROMPT` und die Agenten-Prompts zu. Prompts beim Verschieben also
**wortgleich** lassen; eine Prompt-Änderung gehört nicht in dieses Refactoring.

**Reine Verschiebe-Commits getrennt halten.**
`git log --follow` bleibt nur brauchbar, wenn ein Commit entweder verschiebt oder ändert,
nicht beides. Deshalb sind Schritt 3 (verschieben) und Schritt 4 (zerlegen) getrennt.
`git mv` benutzen, nicht löschen und neu anlegen.

**Keine Rückwärts-Kompatibilitäts-Aliase.**
`src/routes/__init__.py` führt schon einen `chat_router`-Alias "for backward
compatibility". Das Projekt hat genau einen Nutzer und keine externen Importeure — hier
besser direkt umbenennen, statt die nächste Alias-Schicht anzulegen. Insbesondere
`src/agentic/__init__.py` **nicht** als Kompatibilitäts-Fassade für die alten
`src.agents...`-Pfade stehen lassen: dann hätte das Refactoring zwei gültige Importwege statt einem.

---

## 7. Was der Plan nicht löst

Ehrlich zur Abgrenzung, damit das Refactoring nicht als Lösung für Anderes gilt:

- **Die Testordner spiegeln die neue Struktur nicht.** `src/tests/` hat heute
  `engine/`, `agents/`, `routes/`, `unit/`, `live/`, `fakes/`. Nach dem Refactoring wäre
  `tests/tools/` konsequent (statt Tool-Tests in `tests/agents/`), und
  `tests/unit/test_strip_json_fence.py` gehört dann nach `tests/engine/`. Bewusst nicht
  Teil dieses Plans, weil es den Diff vergrößert, ohne am Produktionscode etwas zu ändern.
- **`src/schemas/` bleibt nach Agenten benannt** (`librarian_schema.py`,
  `task_agent_schema.py`, ...). Nach dem Refactoring passt die Agenten-Benennung dort
  sogar besser, weil die Tool-Argumente heraus sind — aber eine Spiegelung der neuen
  Paketstruktur in `schemas/` ist nicht Teil dieses Plans.
- **`_run_turn` bleibt eine lange Schleife.** Schritt 4 nimmt die Fachlogik heraus,
  aber die Zustandsmaschine (Tool-Runden, Parse-Retries, erzwungene finale Antwort)
  bleibt eine Funktion. Sie weiter zu zerlegen ist eine eigene, gefährlichere Aufgabe.
- **Keine Verhaltensänderung.** Keine Prompts, keine Modelle, keine Limits, keine
  Werkzeug-Beschreibungen. Wenn ein Test nach einem Schritt anders läuft als vorher,
  ist das ein Fehler im Schritt, nicht ein Ergebnis.

---

## 8. Übergabe an eine andere Person oder einen Agenten

**Vorher committen.** Der Arbeitsbaum enthält beim Schreiben dieses Plans 48
uncommittete Änderungen, darunter ein komplettes vorangegangenes Refactoring:
`src/core/`, `src/routes/` und `src/tests/` sind neue, von git noch nie gesehene
Verzeichnisse, und zehn alte flache Module (`src/llm_engine.py`,
`src/obsidian_processor.py`, ...) sind gelöscht, aber nicht committet. Dieses
Refactoring darauf aufzusetzen, geht schief:

- `git mv` (Schritt 6, Abschnitt 6) funktioniert nur für getrackte Dateien. Auf
  untracked Dateien gibt es keine Historie, der man folgen könnte.
- Ein fehlgeschlagener Schritt lässt sich nicht zurücknehmen — `git checkout .`
  würde das vorherige Refactoring mitreißen.
- Der Diff des neuen Refactorings ist nicht vom Bestehenden zu trennen, also auch
  nicht prüfbar.

Also zuerst den aktuellen Stand committen, dann Schritt 1 beginnen. Nebenbei gehören
`.coverage` und die generierten Vault-Artefakte (`data.example/.ai_map.json`,
`data.example/**/.index.md`) in die `.gitignore` — sie entstehen bei jedem Testlauf neu.

**Abnahmekriterium.** Die Testsuite ist vor dem Refactoring grün: **168 bestanden,
1 deselektiert** (der `live`-Test, der echte API-Aufrufe macht) in ~4 Sekunden, via
`.venv/bin/python -m pytest -q`. Nach *jedem* Schritt muss genau diese Zahl wieder
stehen. Schritt 4 fügt neue Tests in `tests/engine/test_guards.py` hinzu, erhöht die
Zahl also absichtlich; sonst ist jede Abweichung ein Fehler im Schritt. Die Suite
braucht kein Netz und keinen API-Key — wenn ein Test plötzlich hängt oder langsam
wird, ist ein Monkeypatch-Pfad aus Abschnitt 6 ins Leere gelaufen und es gehen echte
Anfragen raus.

**`build_task_input` im Beispiel von Abschnitt 4 existiert noch nicht.** Das ist der
Name für die Hilfsfunktion, die beim Herausziehen von `engine/jobs.py` (Schritt 6) in
`agents/task_agent.py` neu entsteht: Sie baut den `TaskAgentInput` (heute inline in
`_run_job`, inklusive `format_ai_map(load_ai_map())`), damit `engine/jobs.py` den
Input-Aufbau nicht kennen muss. Nicht danach suchen — anlegen.

---

## 9. Die Agenten-Schicht als eigenes Modul

Frage war, ob `agentic` ein eigenes Modul werden sollte. Dafür zuerst die Zahlen, weil
sie die Antwort tragen.

### 9.1 Die tatsächliche Schnittstelle

Was die Schicht **nach Schritt 1** von außen importiert — vollständig:

| Aus | Was | Umfang |
|---|---|---|
| `src/schemas/` | `WikiAgent`, `AgentSession`, `SessionMessage`, `MessageRole`, `ToolCall`, `LLMCall`, `WikiTool`, `AgentStatus`, `LLMModels`, `FALLBACK_MAP` + die In/Out-Modelle je Agent + Tool-Argumente | ~25 Namen |
| `src/navigation/` | `load_ai_map`, `format_ai_map`, `load_file`, `load_files`, `load_file_summary`, `load_file_summaries`, `load_directory_summary`, `load_directory_summaries`, `create_directory`, `create_file`, `edit_file`, `move_file`, `delete_file` | 11 Funktionen |
| `src/core/logging_config` | `logger`, `SessionLogger` | 2 Namen |

`src.core.obsidian_processor` und `src.core.scheduler` tauchen heute nur in
`map_maintenance.py` auf und verschwinden mit Schritt 1 aus der Schicht.

Wer die Schicht umgekehrt nutzt — ebenfalls vollständig, ohne Tests:

| Importeur | Was |
|---|---|
| `routes/session/post_session.py` | `start_wiki_chat` |
| `routes/session/post_message.py` | `continue_wiki_chat` |
| `core/obsidian_processor.py:282,315` | `run_agent_session`, `SummarizerAgent`, `FolderSummarizerAgent` (schon heute verzögert importiert) |

Drei Kanten hinein, zwei Nutzer hinaus. Die Grenze ist also schon fast sauber.

### 9.2 Eigenes Paket? Nein. Erzwungene Grenze? Ja.

**Als installierbares Paket (eigenes `pyproject.toml`, eigenes Repo) lohnt es nicht.**
Wiederverwendbar wäre die Schicht erst, wenn sie *diesen* Vault nicht mehr kennt — heute
sind die Prompts fest verdrahteter deutscher Weltenbau-Text, die Werkzeuge binden
konkret an `src.navigation`, und der `SessionLogger` schreibt in das `logs/` dieses
Projekts. Diese drei Kanten in Protokolle zu invertieren ist ein größeres Projekt als
dieses Refactoring, und es gibt keinen zweiten Nutzer, der es bezahlt.

**Was sich lohnt, ist die Grenze selbst — und die ist fast geschenkt:**

1. **`SessionLogger` gehört in die Engine.** Produktiv nutzt ihn genau eine Datei
   (`llm_engine.py:62`). Er protokolliert Agenten-Sessions, das ist Aufgabe der Engine
   und nicht der Vault-Verwaltung. Danach schrumpft die `core`-Abhängigkeit der Schicht
   auf `logger`. Eingeplant in Schritt 4.

2. **`logging_config` sollte danach nicht mehr in `src/core/` liegen.** Hier steckt ein
   echter Paket-Zyklus: `agentic` importiert `core.logging_config`, während
   `core.obsidian_processor` `agentic` importiert — genau deshalb stehen die Importe dort
   schon heute verzögert im Funktionskörper. `src/navigation/` importiert ebenfalls aus
   `core`. `logging_config.py` selbst importiert nichts außer der Standardbibliothek.
   Ein Modul, von dem alle abhängen und das von nichts abhängt, gehört nicht in eine
   Schicht, die über ihm liegt — vor dem letzten Refactoring lag es als
   `src/logging_config.py` richtig. Zurückgezogen (dorthin oder nach `src/infra/`) wird
   die Schichtung zyklenfrei:

   ```
   logging    -> (nur stdlib)
   schemas    -> (nur pydantic)
   navigation -> schemas, logging
   agentic    -> schemas, navigation, logging
   core       -> schemas, navigation, logging, agentic (verzögert)
   routes     -> agentic, core
   ```

   **Nicht Teil dieses Plans:** Der Schritt berührt `src/core/` und `src/navigation/`
   genauso wie `agentic` und ist deshalb ein eigenes, kleines Folge-Refactoring — er
   sollte nicht in diese Schrittliste geschmuggelt werden. Hier notiert, damit er nicht
   verloren geht.

3. **Die Fassade aus 2.3 plus der ast-Scan-Test aus Abschnitt 6.** Zusammen sind sie
   der einzige Teil von "eigenes Modul", der im Alltag wirklich etwas bringt: eine
   benannte Schnittstelle von fünf Namen, und eine Prüfung, die beim Testlauf anschlägt,
   wenn jemand daran vorbeigreift.

   **Was hier bewusst *nicht* gemacht wird:** die Gegenrichtung als Fassade, also ein
   `agentic/ports.py`, das die 11 `src.navigation`-Funktionen und `logger`
   re-exportiert, damit die Schicht nur noch aus sich selbst importiert. Das klingt
   symmetrisch, macht den Code aber schlechter lesbar — `from src.agentic.ports import
   load_files` sagt weniger als `from src.navigation import load_files`, das verrät, wo
   die Daten herkommen. Der einzige Gewinn wäre, die Vault-Implementierung austauschen
   zu können, und dafür gibt es keinen Anlass. Nötig wird diese Inversion erst für ein
   verteilbares Paket (siehe oben) — und dann als `Protocol` mit Injektion, nicht als
   Re-Export, weil Re-Exporte die Indirektionskosten bringen, ohne tatsächlich zu
   entkoppeln.

Fazit: Punkte 1 und 3 gehören in dieses Refactoring (Schritt 4 bzw. 6), Punkt 2 ist ein
eigener kleiner Folgeschritt danach. Ein echtes verteilbares Paket ist erst sinnvoll,
wenn es einen zweiten Vault oder ein zweites Projekt gibt — dann ist Punkt 1 bis 3
genau die Vorarbeit, die es braucht.
