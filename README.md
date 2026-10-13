# Obsidian Vault Agents

Eine selbstgehostete Agenten-Engine für einen persönlichen **Obsidian-Vault**.
Sie beobachtet den Vault im Hintergrund, hält für jede Datei und jeden Ordner
KI-Zusammenfassungen aktuell und stellt einen Chat bereit, der über diese
Zusammenfassungen navigiert, statt blind durch alle Dateien zu greppen.

Entstanden ist das Projekt für ein Science-Fiction-Weltenbau-Wiki, bei dem der
Vault schneller wächst, als man ihn im Kopf behält: Wer ist noch mal mit wem
verfeindet, und in welcher Datei stand die Regel zum Warp-Antrieb? Die Engine
läuft auf einem Raspberry Pi, die Inhalte bleiben lokal.

## Der eigentliche Punkt: das Ganze kostet nichts

Alles, was hier beschrieben wird — sieben Agenten, Zusammenfassungs-Pipeline,
Chat, Websuche, Hintergrund-Aufgaben — läuft vollständig auf dem **kostenlosen
Free Tier von Google AI Studio**. Man braucht genau eine Sache, um es selbst zu
betreiben: einen `GEMINI_API_KEY`, den man sich in zwei Minuten kostenlos
anlegt. Keine Kreditkarte, kein Abo, keine Vektordatenbank, kein gehosteter
Dienst, keine Nutzungsabrechnung. Ausser dem Strom für den Raspberry Pi
entstehen keine laufenden Kosten — dauerhaft, nicht als Testphase.

Das ist keine Nebenbemerkung, sondern die Vorgabe, aus der die Architektur
entstanden ist: Verwendet werden ausschliesslich Modelle, die im Free Tier
verfügbar sind (Gemini Flash-Lite und Gemma), und auch die Websuche nutzt
Search Grounding im Free Tier. Debouncing, Modell-Kaskade, Modell-Rotation und
Kontext-Kompaktierung sind alle genau dafür da, mit diesen Kontingenten
auszukommen (siehe [Kosten: keine](#kosten-keine)).

Wer einen eigenen Obsidian-Vault und einen Raspberry Pi (oder irgendeinen
Rechner mit Docker) hat, kann das hier also ohne jede Ausgabe nachbauen.

---

## Das Grundproblem

Ein gewachsener Wissens-Vault ist für ein LLM schlecht durchsuchbar. Volltextsuche
über hunderte Markdown-Dateien liefert entweder zu viel oder das Falsche, und der
gesamte Vault passt nicht ins Kontextfenster.

Die Engine legt deshalb eine **navigierbare Zwischenschicht** an:

| Artefakt | Inhalt |
|---|---|
| `.ai_map.json` | zentrale Karte: jede Datei und jeder Ordner mit Ein-Satz-Zusammenfassung |
| `<Ordner>/.index.md` | ausführlichere Ordner-Zusammenfassung im YAML-Frontmatter |
| `linked_files` | pro Datei die Ziele ihrer Obsidian-Wikilinks, als Frontmatter |

Ein Agent liest erst die Karte, entscheidet dort, welche Dateien relevant sind,
und öffnet nur diese. Das ersetzt eine Vektordatenbank durch etwas, das man auch
selbst lesen kann — die Artefakte liegen als normale Dateien im Vault.

## Architektur

```
Obsidian-Vault ──> watchdog ──> Scheduler (debounced) ──> Summarizer-Agenten
     ^                                                          │
     │                                                          v
     └────────────── .ai_map.json / .index.md <─────────────────┘
                              │
                              v
                       Chat-Agent (ReAct)
                       ├── ask_librarian      Suche über die Karte
                       ├── create/edit/move   Änderungen am Vault
                       ├── deep_reasoning     langer Kontext, hohes Thinking
                       ├── web_search         Google Search Grounding
                       └── start_background_task ──> Task-Agent (eigener Thread)
```

### Paketstruktur (`src/`)

- `src/agentic/` — Kapselt die gesamte KI- und Agenten-Schicht hinter einer schlanken Fassade (`src/agentic/__init__.py`):
  - `agents/`: Roster aller Agenten (`ChatAgent`, `TaskAgent`, `LibrarianAgent`, `Summarizer`, `FolderSummarizer`, `reasoner`, `web_search`)
  - `engine/`: ReAct-Ausführungsschleife (`runner.py`), Kontext-Kompaktierung (`compaction.py`), Job-Registry (`jobs.py`), Absicherungen (`guards.py`), Response-Parsing (`response.py`), Sitzungslogs (`session_log.py`) und Modell-Rotation (`model_rotation.py`)
  - `tools/`: Modulare Werkzeugdefinitionen (`vault_read.py`, `vault_write.py`, `delegation.py`, `tasks.py`)
- `src/core/` — Vault-Verwaltung, Watchdog, Scheduler, Kartenpflege (`map_maintenance.py`), Rebuild
- `src/navigation/` — Dateisystem- und YAML-Zugriff auf den Obsidian-Vault
- `src/routes/` — FastAPI HTTP-Endpunkte für Chat-Sessions und Datei-Operationen
- `src/schemas/` — Pydantic-Datenmodelle und Werkzeug-Argumente

### Agenten

| Agent | Aufgabe |
|---|---|
| **Chat** | beantwortet Fragen im Dialog, ruft die übrigen Agenten als Werkzeuge auf |
| **Task** | arbeitet mehrschrittige Aufgaben eigenständig ab: plant erst, hakt Schritte ab, berichtet am Ende |
| **Librarian** | findet relevante Dateien über die Karte statt über Volltextsuche |
| **Summarizer** | Zusammenfassung einzelner Dateien |
| **Folder-Summarizer** | Zusammenfassung ganzer Ordner, kaskadiert nach oben |
| **Reasoner** | längere Ausarbeitungen mit viel Kontext, hohes Thinking-Budget |
| **Web-Search** | Faktenchecks gegen das echte Internet |

## Der agentische Workflow in Kurzform

Ausführlich dokumentiert in [docs/agentic-workflow.md](docs/agentic-workflow.md) —
hier die Kurzfassung.

**Zwei Arten von Agenten.** Fünf Agenten (Chat, Task, Librarian, Summarizer,
FolderSummarizer) sind deklarative `WikiAgent`-Definitionen — System-Prompt,
Eingabe-Schema, Antwort-Schema, Werkzeuge, Rundenbudget — und laufen über
dieselbe Ausführungsschleife via `litellm`. Reasoner und Web-Search sind dagegen
einzelne SDK-Aufrufe ohne Session und ohne Werkzeuge; sie existieren nur als
Werkzeug anderer Agenten und geben im Fehlerfall einen lesbaren Fehlertext
zurück statt zu werfen.

**Ein Turn.** `engine/runner.py` führt pro Aufruf einen Turn aus: Kontext aus
der Session bauen, Modell aufrufen, Werkzeug-Aufrufe ausführen und als
Nachrichten anhängen, wiederholen — bis das Modell keine Werkzeuge mehr
anfordert und stattdessen die finale Antwort liefert. Diese wird gegen das
Antwort-Schema geparst; schlägt das fehl, geht der konkrete Fehlerbericht
zurück ans Modell (bis `max_retries`). Eine Runde vor dem Iterationslimit
werden die Werkzeuge entzogen und eine finale Antwort erzwungen, statt die
Session ergebnislos abzubrechen.

**Die Session ist die einzige Quelle der Wahrheit.** Der Kontext jedes
Modellaufrufs entsteht ausschliesslich aus `AgentSession.messages` — daneben
wird nichts mitgeführt. Genau deshalb kann die Kompaktierung einfach diese
Liste umschreiben.

**Absicherungen gegen halluzinierte Arbeit.** Zwei Prüfungen verwerfen eine
syntaktisch gültige finale Antwort und erzwingen einen Retry: eine Antwort ganz
ohne Werkzeug-Aufruf bei Agenten, die laut Prompt immer eines nutzen müssen
(Task-Agent: `update_plan`), und eine Antwort, die eine Dateiänderung behauptet
("lege ich dir an", "wurde erstellt"), ohne dass je ein schreibendes Werkzeug
aufgerufen wurde.

**Drei Abläufe.** (1) *Chat*: HTTP-Request → Chat-Agent mit ai_map und ggf. der
im Editor geöffneten Notiz im Kontext → ReAct-Runden → Antwort plus Liste der
tatsächlich ausgeführten Vault-Änderungen. (2) *Hintergrund-Aufgabe*: Der
Chat-Agent startet den Task-Agenten in einem eigenen Thread und bekommt sofort
eine `task_id`; dessen Plan liegt als reiner Zustand in der Job-Registry, eine
Statusabfrage kostet daher keinen Modellaufruf. (3) *Zusammenfassung*: Watchdog
→ debounced Scheduler → Summarizer → Frontmatter und `.ai_map.json` → Ordner-
Zusammenfassung, die nur bei echter Änderung eine Ebene weiter nach oben
kaskadiert.

**Verschachtelte Sessions.** Ruft der Chat-Agent `ask_librarian` auf, läuft
darin eine komplette zweite Agenten-Session mit eigenem Budget und eigenem
Logfile. Sie liefert Antwort, Quellenpfade *und* den Volltext dieser Quellen
zurück, damit der Aufrufer sie nicht erneut laden muss.

**Nachvollziehbarkeit.** Jede Session schreibt eine Markdown-Logdatei nach
`logs/llm_details/` — pro Schritt der komplette gesendete Kontext, die rohe
Antwort, Tokenzahlen und alle Werkzeug-Aufrufe mit Ergebnis. Fehlverhalten
lässt sich damit meist direkt am Log ablesen.

## Details, die den Unterschied machen

**Debouncing statt Dauerfeuer.** Zusammenfassungen entstehen erst 30 Minuten nach
der letzten Änderung an einer Datei. Ordner-Zusammenfassungen kaskadieren mit
doppeltem Zeitfenster nach oben — und nur dann eine Ebene weiter, wenn sich auf
der aktuellen Ebene tatsächlich etwas geändert hat. Ohne das würde jede
Tippkorrektur in einer tief verschachtelten Datei die gesamte Kette bis zur
Wurzel neu berechnen.

**Kontext-Kompaktierung.** In langen ReAct-Sessions wird bei jedem Aufruf der
komplette Verlauf erneut gesendet, der Tokenverbrauch wächst also quadratisch.
Der Compactor ersetzt den älteren Teil des Verlaufs durch eine mit einem
günstigen Modell erzeugte Zusammenfassung und behält System-Prompt, Aufgabe und
die letzten Runden im Original.

**Modell-Kaskade.** Schlägt ein Modell fehl oder ist das Kontingent erschöpft,
fällt die Engine über eine Fallback-Kette auf schwächere Modelle zurück, statt
die Sitzung abzubrechen.

**Der Task-Agent läuft nebenläufig.** Er startet in einem eigenen Thread, damit
der Chat nicht blockiert; sein Fortschritt liegt in einer Job-Registry, sodass
`check_task_status` ihn abfragen kann, ohne eine neue LLM-Sitzung anzustossen.

**Schreibende Werkzeuge mit unscharfer Pfadauflösung.** Agenten dürfen Dateien
anlegen, ändern und verschieben. Da Modelle Pfade selten exakt treffen
(`Technologie/Antriebe` vs. `./data/Technologie/Antriebe.md`), löst die
Navigationsschicht Pfade tolerant auf und meldet Mehrdeutigkeiten zurück,
statt einfach die erstbeste Datei zu nehmen.

## Technik

Python, FastAPI, watchdog, `litellm` als Provider-Abstraktion, Google GenAI SDK
für Search Grounding, Antigravity SDK für den Reasoner, pydantic-Schemas für alle
Werkzeuge und Agenten-Ein-/Ausgaben, Docker Compose fürs Deployment.
Rund 3.400 Zeilen Python.

## Kosten: keine

Wie oben beschrieben läuft das gesamte System auf dem **kostenlosen Kontingent
von Google AI Studio**. Vier Architekturentscheidungen ergeben sich direkt
daraus:

- **Debouncing** verhindert, dass jede einzelne Änderung sofort einen Modellaufruf
  auslöst. Wer beim Schreiben alle paar Sekunden speichert, würde ein Kontingent
  sonst in Minuten aufbrauchen.
- **Die Modell-Kaskade** fängt erschöpfte Ratenlimits ab: Statt abzubrechen, fällt
  die Engine auf das nächstschwächere Modell zurück, das noch Kontingent hat.
- **Die Modell-Rotation** verteilt die Last auf zwei Kontingente, weil das
  Tokens/Minute-Limit pro Modell gilt: Librarian-Anfragen wechseln sich zwischen
  zwei Gemma-Modellen ab, Hintergrund-Aufgaben zwischen zwei Flash-Lite-Modellen.
- **Die Kontext-Kompaktierung** hält den pro Runde gesendeten Verlauf klein —
  ohne sie läuft eine lange Task-Session allein durch ihren mitgeschleppten
  Kontext ins Limit.

Wer mehr Durchsatz braucht, kann über `litellm` jeden anderen Anbieter
einhängen — dann fallen dessen Kosten an.

## Start

```bash
cp .env.example .env      # GEMINI_API_KEY eintragen
docker compose up --build
```

Danach läuft die Engine auf `http://localhost:8000`, das Chat-Frontend liegt
unter `/`. Ohne weitere Konfiguration arbeitet sie auf dem mitgelieferten
Demo-Vault `data.example/`. Für den eigenen Vault in der `.env`:

```
VAULT_PATH=/pfad/zum/obsidian-vault
```

Ein vollständiger Erstdurchlauf über einen bestehenden Vault:

```bash
docker compose exec world-engine python -m src.core.rebuild
```

## Hinweis

Persönliches Projekt, gewachsen um einen konkreten eigenen Anwendungsfall — kein
Produkt und nicht auf Allgemeingültigkeit ausgelegt. Die System-Prompts sind auf
Deutsch und auf Weltenbau zugeschnitten; für andere Vaults müsste man sie anpassen.

---

Robin Feldmann · [github.com/Freshpinguin](https://github.com/Freshpinguin)
