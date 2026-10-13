# Obsidian Vault Agents

Eine selbstgehostete Agenten-Engine für einen persönlichen **Obsidian-Vault**.
Sie beobachtet den Vault im Hintergrund, hält für jede Datei und jeden Ordner
KI-Zusammenfassungen aktuell und stellt einen Chat bereit, der über diese
Zusammenfassungen navigiert, statt blind durch alle Dateien zu greppen.

Entstanden ist das Projekt für ein Science-Fiction-Weltenbau-Wiki, bei dem der
Vault schneller wächst, als man ihn im Kopf behält: Wer ist noch mal mit wem
verfeindet, und in welcher Datei stand die Regel zum Warp-Antrieb? Die Engine
läuft auf einem Raspberry Pi, die Inhalte bleiben lokal.

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

Das gesamte System läuft auf dem **kostenlosen Kontingent von Google AI Studio**.
Verwendet werden ausschliesslich Modelle, die dort im Free Tier verfügbar sind
(Gemini Flash-Lite und Gemma), und auch die Websuche nutzt Search Grounding im
Free Tier. Ausser dem Strom für den Raspberry Pi entstehen keine laufenden Kosten.

Zwei Architekturentscheidungen ergeben sich direkt daraus:

- **Debouncing** verhindert, dass jede einzelne Änderung sofort einen Modellaufruf
  auslöst. Wer beim Schreiben alle paar Sekunden speichert, würde ein Kontingent
  sonst in Minuten aufbrauchen.
- **Die Modell-Kaskade** fängt erschöpfte Ratenlimits ab: Statt abzubrechen, fällt
  die Engine auf das nächstschwächere Modell zurück, das noch Kontingent hat.

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
