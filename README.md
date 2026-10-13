<p align="center">
  <img src="assets/logo.jpg" alt="Obsidian Vault Agents" width="360" />
</p>

<h1 align="center">Obsidian Vault Agents</h1>

<p align="center">
  <strong>A self-hosted agent engine for personal Markdown knowledge bases.</strong><br />
  It keeps AI summaries of every file and folder current, and answers questions by
  navigating those summaries instead of grepping the whole vault.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license" />
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Docker%20Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose" />
  <img src="https://img.shields.io/badge/tests-215%20passing-success" alt="215 tests" />
  <img src="https://img.shields.io/badge/runs%20on-Raspberry%20Pi-C51A4A?logo=raspberrypi&logoColor=white" alt="Runs on Raspberry Pi" />
</p>

---

Obsidian Vault Agents watches an Obsidian vault in the background, maintains a
machine-readable map of its contents, and exposes a web interface where a chat
agent can read, search, create, edit and move notes on your behalf. Everything
runs on your own hardware — a Raspberry Pi is enough — and your notes never
leave it except as prompts to the model provider you configure.

## Demo

> _A short screen recording of the application will go here._

<!--
  TODO: replace with the recording, e.g.
  https://github.com/user-attachments/assets/<id>
-->

## The problem

A knowledge vault that has grown organically is difficult for a language model
to search. Full-text search across hundreds of Markdown files returns either
too much or the wrong thing, and the vault as a whole does not fit into a
context window.

The engine therefore maintains a **navigable intermediate layer**:

| Artifact | Contents |
|---|---|
| `.ai_map.json` | Central map: every file and folder with a one-sentence summary |
| `<folder>/.index.md` | A longer folder summary in YAML frontmatter |
| `linked_files` | Per file, the targets of its Obsidian wikilinks, as frontmatter |

An agent reads the map first, decides there which files are relevant, and opens
only those. This replaces a vector database with something you can also read
yourself — the artifacts are plain files inside the vault.

## Architecture

```
Obsidian vault ──> watchdog ──> Scheduler (debounced) ──> Summarizer agents
     ^                                                          │
     │                                                          v
     └────────────── .ai_map.json / .index.md <─────────────────┘
                              │
                              v
                       Chat agent (ReAct)
                       ├── ask_librarian      search across the map
                       ├── create/edit/move   vault mutations
                       ├── deep_reasoning     long context, high thinking budget
                       ├── web_search         Google Search grounding
                       └── start_background_task ──> Task agent (own thread)
```

### Agents

| Agent | Responsibility |
|---|---|
| **Chat** | Answers questions conversationally; calls the other agents as tools |
| **Task** | Works through multi-step assignments autonomously: plans first, ticks off steps, reports at the end |
| **Librarian** | Locates relevant files via the map rather than full-text search |
| **Summarizer** | Summarizes individual files |
| **Folder summarizer** | Summarizes whole folders, cascading upward |
| **Reasoner** | Longer elaborations with large context and a high thinking budget |
| **Web search** | Fact-checks against the live internet |

## How the agent runtime works

Documented in full in [docs/agentic-workflow.md](docs/agentic-workflow.md); the
short version follows.

**Two kinds of agent.** Five agents (Chat, Task, Librarian, Summarizer, Folder
summarizer) are declarative `WikiAgent` definitions — system prompt, input
schema, response schema, tools, turn budget — and all run through the same
execution loop via `litellm`. Reasoner and web search are single SDK calls
without a session and without tools; they exist only as tools for other agents
and return readable error text instead of raising.

**One turn.** `engine/runner.py` executes one turn per invocation: build context
from the session, call the model, execute requested tool calls and append them
as messages, repeat — until the model stops requesting tools and returns a final
answer instead. That answer is parsed against the response schema; if parsing
fails, the concrete error report goes back to the model (up to `max_retries`).
One round before the iteration limit, tools are withdrawn and a final answer is
forced, rather than ending the session without a result.

**The session is the single source of truth.** The context of every model call
is derived exclusively from `AgentSession.messages`; nothing is carried
alongside it. That is precisely why compaction can simply rewrite this list.

**Guards against hallucinated work.** Two checks discard a syntactically valid
final answer and force a retry: an answer with no tool call at all from agents
whose prompt requires one (the task agent's `update_plan`), and an answer that
claims a file change ("I've created that for you") without any writing tool
having been invoked.

**Three flows.** (1) *Chat*: HTTP request → chat agent with the ai_map and, if
present, the note currently open in the editor → ReAct rounds → answer plus a
list of the vault changes actually performed. (2) *Background task*: the chat
agent starts the task agent in its own thread and immediately receives a
`task_id`; the plan lives as pure state in the job registry, so a status query
costs no model call. (3) *Summarization*: watchdog → debounced scheduler →
summarizer → frontmatter and `.ai_map.json` → folder summary, which cascades one
level further up only on a genuine change.

**Nested sessions.** When the chat agent calls `ask_librarian`, a complete
second agent session runs inside it with its own budget and its own log file. It
returns an answer, source paths *and* the full text of those sources, so the
caller does not have to load them again.

**Traceability.** Every session writes a Markdown log to `logs/llm_details/` —
per step the complete context sent, the raw response, token counts and all tool
calls with their results. Misbehaviour can usually be read straight off the log.

## Design decisions

**Debouncing instead of continuous fire.** Summaries are produced only 30
minutes after the last change to a file. Folder summaries cascade upward on a
doubled time window — and only one level further when something actually changed
at the current level. Without this, every typo correction in a deeply nested file
would recompute the entire chain up to the root.

**Context compaction.** In long ReAct sessions the full history is re-sent on
every call, so token consumption grows quadratically. The compactor replaces the
older part of the history with a summary generated by a cheap model, and keeps
the system prompt, the assignment and the most recent rounds verbatim.

**Model cascade.** If a model fails or its quota is exhausted, the engine falls
back along a chain to weaker models instead of aborting the session.

**The task agent runs concurrently.** It starts in its own thread so the chat
does not block; its progress lives in a job registry, so `check_task_status` can
query it without starting a new LLM session.

**Writing tools with fuzzy path resolution.** Agents may create, modify and move
files. Since models rarely get paths exactly right (`Technology/Propulsion` vs.
`./data/Technology/Propulsion.md`), the navigation layer resolves paths
tolerantly and reports ambiguities back instead of simply taking the first
match.

## Codebase

Roughly 5,400 lines of production Python and 3,800 lines of tests (215 offline, plus an opt-in live suite),
plus a dependency-free vanilla-JS frontend. The layering is enforced by a test
(`src/tests/unit/test_import_boundaries.py`) rather than by convention alone.

```
src/
├── agentic/        AI and agent layer, behind one slim facade (agentic/__init__.py)
│   ├── agents/     The agent roster: chat, task, librarian, summarizer,
│   │               folder_summarizer, reasoner, web_search
│   ├── engine/     ReAct loop (runner.py), context compaction (compaction.py),
│   │               job registry (jobs.py), hallucination guards (guards.py),
│   │               response parsing (response.py), session logs (session_log.py),
│   │               model rotation (model_rotation.py)
│   └── tools/      Modular tool definitions: vault_read, vault_write,
│                   delegation, tasks
├── core/           Vault supervision: watchdog handling, debounced scheduler,
│                   map maintenance, backups, full rebuild
├── navigation/     The only layer that touches the filesystem: path resolution,
│                   YAML frontmatter, vault mutations
├── routes/         FastAPI endpoints, one file per endpoint, grouped by resource
│                   (session, files, frontend, health)
├── schemas/        Pydantic models for every agent I/O and tool argument
├── tests/          Unit, agent, engine and route tests, plus an opt-in live suite
└── main.py         Application entrypoint: FastAPI app, watchdog, background threads
```

Two conventions are worth knowing before reading further:

- **Agents are data, not code.** An agent is a `WikiAgent` declaration
  (prompt, schemas, tools, budget) interpreted by the shared runner. Adding an
  agent means adding a definition, not a new execution path.
- **Only `navigation/` touches the vault.** Everything above it works through
  that layer, which is what makes the fuzzy path resolution and the mutation
  guarantees hold everywhere.

The frontend is plain HTML, CSS and JavaScript in `index.html` and `static/`
(no build step): a three-pane shell with a file explorer, a note viewer/editor
with rendered and raw modes, and the chat pane, kept in sync with the backend
over server-sent events.

## Quick start

```bash
cp .env.example .env      # add your GEMINI_API_KEY
docker compose up --build
```

The engine then runs at `http://localhost:8000`, with the chat frontend at `/`.
With no further configuration it operates on the bundled demo vault
`data.example/`.

A full initial pass over an existing vault:

```bash
docker compose exec world-engine python -m src.core.rebuild
```

## Configuration

All configuration lives in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — | Google AI Studio key (required) |
| `VAULT_PATH` | `./data.example` | Path to your own Obsidian vault |
| `BACKUP_INTERVAL_MINUTES` | `720` | Interval for the automatic git backup |
| `MAP_MAINTENANCE_INTERVAL_MINUTES` | `60` | Interval for `.ai_map.json` consistency maintenance |

`docker-compose.yml` additionally contains a commented-out Syncthing service for
synchronizing the vault across several devices, and a commented-out SSH mount for
pushing the automatic backup to a remote git repository.

## Development

```bash
pip install -r requirements-dev.txt
pytest                                   # 215 tests, no API calls
OVA_LIVE_TESTS=1 pytest -m live          # opt-in: real LLM calls, consumes quota
```

The default test run is fully offline: model providers are replaced by fakes in
`src/tests/fakes/`. The live suite is deselected unless explicitly requested.

## Operating cost

The engine is built to run inside the **free tier of Google AI Studio**. It
requires exactly one thing to operate: a `GEMINI_API_KEY`, which is free to
create. No vector database, no hosted service, no usage billing.

This was a design constraint rather than an afterthought, and four architectural
decisions follow directly from it:

- **Debouncing** prevents every individual edit from triggering a model call.
  Saving every few seconds while writing would otherwise exhaust a quota in
  minutes.
- **The model cascade** absorbs exhausted rate limits: instead of aborting, the
  engine falls back to the next weaker model that still has quota.
- **Model rotation** spreads load across two quotas, because the tokens-per-minute
  limit applies per model: librarian requests alternate between two Gemma models,
  background tasks between two Flash-Lite models.
- **Context compaction** keeps the per-round history small — without it a long
  task session runs into the limit on its carried context alone.

Only free-tier models are used (Gemini Flash-Lite and Gemma), and web search
uses free-tier Search grounding. If you need more throughput, any other provider
can be plugged in through `litellm`, at that provider's cost.

## Scope

The system is in day-to-day use against a personal vault running on a Raspberry
Pi. Two things to be aware of before pointing it at your own:

- The system prompts are written in German and tuned for a worldbuilding vault.
  Using it for a different domain or language means rewriting the prompts in
  `src/agentic/agents/`.
- Model selection assumes the Google AI Studio free tier. Other providers work
  through `litellm`, but the fallback cascade (`src/schemas/llm_models.py`) and
  the rotation pools (`src/agentic/engine/model_rotation.py`) are configured for
  Gemini and Gemma.

## License

Released under the [MIT License](LICENSE).

---

Robin Feldmann · [github.com/Freshpinguin](https://github.com/Freshpinguin)
