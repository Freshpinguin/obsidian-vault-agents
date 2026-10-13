# The agentic workflow

**Scope:** everything under `src/agentic/` — the agent engine, the agents, the tools — plus the
seams where the rest of the app (`src/core/`, `src/routes/`, `src/navigation/`) enters and leaves it.

**Written for:** an engineer or agent who has to change code in `src/agentic/` and needs to know
what actually happens at runtime, not just what the modules are called.

**Caveat:** `src/agentic/` is being refactored (the package was split out of `src/agents/` in
commits "Schritt 1–5"). Module paths below reflect the tree as committed; a few transitional
re-exports are flagged in [§11](#11-rough-edges-and-transitional-state).

---

## 1. The two substrates

There is no single "agent framework" here. Two different mechanisms coexist, and which one an
agent uses determines everything about how it behaves.

| | **Engine agents** | **SDK one-shots** |
|---|---|---|
| Who | Chat, TaskAgent, Librarian, Summarizer, FolderSummarizer | `run_reasoning`, `web_search` |
| Built from | `WikiAgent` + `AgentSession`, driven by `_run_turn` | a plain function calling a Google SDK directly |
| Transport | `litellm.completion` | `google.antigravity` / `google.genai` |
| Multi-turn | yes (ReAct loop, tool calls, retries) | no — one request, one answer |
| Output | validated Pydantic model | a `str` (including error strings) |
| Logged to | `logs/llm_details/*.md` per session | the normal app log only |

The SDK one-shots are not agents in the engine's sense at all: they exist *only* as tools other
agents call. They never fail with an exception — on error they return a human-readable
`"Fehler: …"` string, because their result is fed straight back into a caller's tool message.

```
                    ┌───────────────────────── engine (litellm) ─────────────────────────┐
HTTP /sessions ───> │ ChatAgent ──tool──> LibrarianAgent                                 │
                    │     │                                                              │
watchdog ─────────> │     │               SummarizerAgent, FolderSummarizerAgent         │
                    │     └──tool──> start_background_task ──thread──> TaskAgent         │
                    └────────┬───────────────────────────────────────────────────────────┘
                             └──tool──> run_reasoning / web_search   (SDK one-shots)
```

---

## 2. The data model

Four Pydantic types carry the whole workflow. All live outside `src/agentic/`, in
[src/schemas/](../src/schemas/) — the engine is deliberately a consumer of those schemas.

### `WikiTool` — [src/schemas/tool_schema.py](../src/schemas/tool_schema.py)

A name, a description, a `parameters` Pydantic model, and a `func`.

- `to_openai_schema()` turns `parameters` into the function-calling JSON schema (stripping
  `title` keys so the model sees a clean schema).
- `call(arguments)` validates the arguments, invokes `func(**args)`, and **always returns a
  string** — invalid arguments and raised exceptions become `"Fehler: …"` text. A tool therefore
  cannot crash a turn; a broken call just becomes a bad tool result the model has to deal with.

`MUTATION_TOOL_NAMES` in the same file is the canonical set of vault-writing tool names. It is
used by the hallucination guard ([§5](#5-guards)) — and, separately and by hand, by
[storage.py:33](../src/routes/session/storage.py#L33) to report mutations to the frontend.

### `WikiAgent` — [src/schemas/agent_schema.py:58](../src/schemas/agent_schema.py#L58)

A declarative agent definition: `system_prompt`, `input_type`, `response_type`, `default_model`,
`temperature`, `tools`, plus the knobs that change loop behaviour:

| Field | Effect |
|---|---|
| `max_retries` (3) | how many invalid final answers are retried before the turn gives up |
| `max_tool_iterations` (15) | hard ceiling on tool rounds per turn; the forced-answer nudge fires one round earlier |
| `enable_context_compaction` | turns on [§6](#6-context-compaction) |
| `compaction_model` / `_threshold_chars` / `_keep_recent_rounds` | compaction tuning |
| `require_tool_call_first_round` | forces `tool_choice="required"` on round 1 **and** rejects any final answer produced with zero tool calls |

`build_response_format_prompt()` generates the "answer as this JSON" instruction from
`response_type`'s field descriptions. This is why field `description=` strings in the schemas are
load-bearing prompt text, not just documentation.

`parse_response()` validates a raw string against `response_type` and, on failure, builds a
German error report that names each bad field, its message, and the offending input — that report
is what gets fed back to the model as the retry prompt.

### `SessionMessage` / `ToolCall` — [src/schemas/agent_schema.py:20-55](../src/schemas/agent_schema.py#L20-L55)

The wire format, one level up from OpenAI's. `to_openai()` handles the three shapes: assistant
message with `tool_calls`, `tool` result message (keyed by `tool_call_id`), and plain text.

### `AgentSession` — [src/schemas/agent_schema.py:185](../src/schemas/agent_schema.py#L185)

The single source of truth for a conversation. Two parallel lists:

- **`messages`** — the conversation itself. `build_messages()` renders it to the litellm
  `messages` array. Nothing is kept alongside it; the context sent on every call is *only* this
  list. That is what makes compaction possible — rewrite `messages` and you have rewritten what
  the model sees.
- **`history`** — one `LLMCall` per model turn (`TOOL_CALL`, `ERROR`, or `SUCCESS`), for logging,
  statistics, and the success check. `is_successful` looks **only at the last entry**, so earlier
  errors in a session are invisible to it; `final_result` is the last entry's `output_data`.

Three initialisers distinguish the session kinds: `start()` wraps the input as a JSON block
("Bitte verarbeite folgende Daten: …") for one-shot task agents; `start_chat()` puts the first
message in as plain prose and optionally appends extra context to the system prompt (this is how
the ai_map gets in); `add_user_message()` extends a live chat.

---

## 3. The turn loop

[src/agentic/engine/runner.py:39](../src/agentic/engine/runner.py#L39) — `_run_turn(session, model_override)`.
This is the heart of the system. It mutates the session in place and returns nothing. One call =
one *turn*: either the entire run of a one-shot agent, or the response to a single chat message.

Setup: resolve the model (`model_override` → `agent.default_model`), look up its fallback chain in
`FALLBACK_MAP`, build the tool schemas, and open (or re-open) the session log file.

Then loop:

1. **Build the request.** `messages = session.build_messages()`; `step = len(history) + 1`, so
   step numbers run continuously across all turns of a chat session.

2. **Tools *or* `response_format`, never both.** While tools are on offer, the expected JSON shape
   is communicated by prompt only — most providers reject function calling combined with a forced
   response format. Once the loop decides no more tools are allowed, `response_format` is set
   ([runner.py:72-90](../src/agentic/engine/runner.py#L72-L90)).

3. **Optionally force the first tool call.** If `require_tool_call_first_round` and
   `tool_steps == 0`, `tool_choice="required"` is set — but only when
   `litellm.utils.supports_tool_choice()` says the model handles it, because the Gemma fallback
   models do not and the request would fail outright.

4. **Call the model.** An exception here records an `ERROR` `LLMCall`, logs the API error, and
   **breaks the loop** — API failures are not retried beyond litellm's own fallback chain.

5. **If the model asked for tools** ([runner.py:117](../src/agentic/engine/runner.py#L117)):
   parse each call's arguments (malformed JSON degrades to `{}`), append one assistant message
   carrying all of them, then execute them **sequentially**, appending a `tool` message per
   result. Unknown tool names come back as a `"Fehler: Unbekanntes Tool …"` string rather than
   raising. Record a `TOOL_CALL` entry, log the step, then:
   - `maybe_compact(...)` — only here, at a clean boundary where no tool call is missing its
     result ([§6](#6-context-compaction));
   - if `tool_steps >= max_tool_iterations - 1`, set `force_final_answer` and append a user
     message ordering an immediate final answer. The next iteration offers no tools, so the loop
     ends with a real answer instead of dying at the hard ceiling.

6. **If the model answered** — strip a stray ```` ```json ```` fence
   ([response.py](../src/agentic/engine/response.py)), parse against `response_type`, append the
   raw text as an assistant message, and run the two guards ([§5](#5-guards)). Valid *and* clean
   → record `SUCCESS`, log, break. Otherwise record `ERROR`, and if `parse_attempts` is still
   within `max_retries`, append the error report as a **user** message and loop again. Note the
   context grows with each retry.

7. On exit, `log_turn_end(session)` writes the interim tally into the session log.

### The three entry points

```python
run_agent_session(agent, raw_input, model_override=None)   # one input → one structured output
start_chat_session(agent, message, model_override, context) # new chat, optional system context
continue_chat_session(session, message, model_override)      # same session_id, same log file
```

All three validate input through `agent.validate_input()` (dict or BaseModel), then call
`_run_turn`. They are re-exported from `src.agentic` and `src.agentic.engine`, which is what the
rest of the app imports.

---

## 4. The agents

[src/agentic/agents/](../src/agentic/agents/). The whole catalogue:

| Agent | Model | Tools | Iter. | Compact | Force tool | In → Out |
|---|---|---|---|---|---|---|
| **Chat** | 3.5-flash-lite | `CONTENT_TOOLS` + `start_background_task`, `check_task_status` | 4 | yes | no | `ChatInput` → `ChatOutput` |
| **TaskAgent** | rotated 3.5/3.1 | `CONTENT_TOOLS` + `update_plan` | 40 | yes | **yes** | `TaskAgentInput` → `TaskAgentOutput` |
| **Librarian** | rotated Gemma 31B/26B | `load_directory_summaries`, `load_file_summaries`, `load_files` | 8 | no | no | `LibrarianInput` → `LibrarianOutput` |
| **Summarizer** | Gemma 31B | — | n/a | no | no | `SummarizerInput` → `SummarizerOutput` |
| **FolderSummarizer** | Gemma 31B | — | n/a | no | no | `FolderSummarizerInput` → `FolderSummarizerOutput` |
| `run_reasoning` | gemini-3.6-flash, thinking HIGH | — (SDK, tools disabled) | n/a | — | — | `(task, file_paths)` → `str` |
| `web_search` | gemini-2.5-flash + Search Grounding | — | n/a | — | — | `(query)` → `str` |

**Chat** ([chat.py](../src/agentic/agents/chat.py)) is the only agent a user talks to.
`start_wiki_chat` / `continue_wiki_chat` wrap the engine with two pieces of context injection:

- the **ai_map** (`format_ai_map(load_ai_map())`) is appended to the system prompt at session
  start, so the agent knows the vault's shape without spending a tool round on it;
- the **active file** in the editor is prefixed onto the user message as
  `[Im Editor geöffnete Notiz: <path> | ai_map Kurzzusammenfassung: <summary>]`, which is how
  "explain *this* note" resolves. Only path and one-line summary — never the file body.

Its budget is deliberately tiny (`max_tool_iterations=4`, so 3 tool rounds before the forced
answer). The prompt pushes anything bigger to `start_background_task`.

**TaskAgent** ([task_agent.py](../src/agentic/agents/task_agent.py)) is the same machinery with a
40-round budget, compaction on, and `require_tool_call_first_round=True`. The prompt is written
against one specific observed failure: the model replying with a plausible, entirely fabricated
success report without ever calling a tool. Hence the explicit "you have exactly two options per
reply" framing, and `update_plan` as a mandatory first move.

**Librarian** ([librarian.py](../src/agentic/agents/librarian.py)) is the navigation specialist:
ai_map in, answer plus `sources` out. Its prompt makes speed explicit — batch all plausible paths
into one call, prefer `load_files` directly when the map is unambiguous, only go through folder
summaries when genuinely lost — and forbids answering from summaries alone.

**Summarizer / FolderSummarizer** are toolless, single-shot, and run from the ingest pipeline,
not from chat ([§8](#8-flow-c-the-summarisation-pipeline)). Both prompts are built around
*stability*: treat the previous summary as good, return it verbatim unless the content genuinely
outgrew it. Without that, every typo would churn the whole map.

---

## 5. Guards

[src/agentic/engine/guards.py](../src/agentic/engine/guards.py). Two checks that reject a
*syntactically valid* final answer and turn it into a retry.

**`check_skipped_required_tool`** — `require_tool_call_first_round` is set but `tool_steps == 0`.
The response is discarded and `SKIPPED_REQUIRED_TOOL_ERROR` is fed back. Belt-and-braces with the
`tool_choice="required"` request flag, which silently does nothing on models that lack support.

**`check_hallucinated_mutation`** — fires only when all of: zero tool calls so far, parse
succeeded, the agent *has* mutation tools, and the `reply` text matches a German
`MUTATION_INDICATORS` keyword ("angelegt", "ich erstelle", "gespeichert", …) together with
`.md` / "datei" / "ordner", and matches no `NEGATIONS` entry ("konnte nicht", "nicht gefunden", …).
In other words: it catches "I've created the file for you!" when nothing was written. The retry
message tells the model to call the tool *now*.

Both are blunt heuristics, by design — they are keyword-based and German-only, and they only look
at the `reply` field of the parsed output. They are a safety net against one expensive failure
mode, not a verification layer.

---

## 6. Context compaction

[src/agentic/engine/compaction.py](../src/agentic/engine/compaction.py). The problem: every round
re-sends the whole history, so token spend over a long ReAct session grows quadratically, and a
single big tool argument (a file body passed to `create_file`) rides along in every subsequent
request forever.

`maybe_compact(session, step, logger)` bails out unless compaction is enabled *and*
`context_size_chars(session) >= compaction_threshold_chars` (default 30 000). That size function
counts `len(m.content)` **plus** the serialised `tool_calls[].arguments`, because the dominant
cost lives in the arguments, not the content — miss that and you systematically under-measure.

When it does run:

```
messages = [ system, first-task-msg ] + [ ...older... ] + [ last N rounds ]
                     head (kept)         → one summary msg      kept verbatim
```

The cut index is chosen from `_round_start_indices()` — the positions of assistant messages —
because cutting anywhere else would separate a tool call from its result and produce an invalid
conversation. If there are not more than `compaction_keep_recent_rounds` (3) assistant messages
after the head, it returns without doing anything.

The older slice is rendered to a transcript and summarised by `compaction_model`
(Gemma 26B) under a prompt that demands concrete facts — which paths were touched, what was
found, what remains open — and explicitly discards written-out file bodies. The result replaces
that slice as a single user message tagged `[Zusammenfassung des bisherigen Verlaufs, …]`.

Every failure path is non-fatal: an SDK error or an empty summary logs and leaves the context
untouched. A successful compaction is written into the session log, because from that step on the
model is seeing something different from the previous step.

---

## 7. Models, cascades and rotation

[src/schemas/llm_models.py](../src/schemas/llm_models.py) holds four free-tier models and a
`FALLBACK_MAP` that cascades downward: 3.5-flash-lite → 3.1-flash-lite → Gemma 31B → Gemma 26B.
The map is passed to litellm as `fallbacks=`, so an exhausted quota or a failing model degrades
the answer instead of ending the session.

On top of that sit two **round-robin rotations**, which solve a different problem — free-tier
tokens-per-minute limits are counted *per model*, so alternating spreads load across two separate
quotas. Both are `ModelRotation` instances from
[engine/model_rotation.py](../src/agentic/engine/model_rotation.py) (`itertools.cycle` behind a
`threading.Lock`, since callers arrive from the FastAPI thread pool and from task threads
concurrently):

- `librarian_rotation` — Gemma 31B / 26B, advanced once per `ask_librarian` call
  ([librarian.py:84](../src/agentic/agents/librarian.py#L84));
- `task_rotation` — 3.5 / 3.1-flash-lite, advanced once per **background task**, not per round
  ([jobs.py:84](../src/agentic/engine/jobs.py#L84)); one task runs start to finish on one model.

---

## 8. The three flows

### Flow A — a chat request

```
POST /sessions                     routes/session/post_session.py
  └─ start_wiki_chat               agents/chat.py       + ai_map, + active-file header
       └─ start_chat_session        engine/runner.py
            └─ _run_turn            ... tool rounds ...
  └─ _sessions[session_id] = session           storage.py  (in-process dict + lock)
  └─ reply_or_502(session)                     → {session_id, reply, mutations[]}

POST /sessions/{id}/messages       → get_session → continue_wiki_chat → same log file
DELETE /sessions/{id}              → drops it from the dict
```

Routes are **sync `def`**, so FastAPI runs them in its thread pool and a chat request occupies a
worker for the whole ReAct loop, nested sub-agents included.

`reply_or_502` ([storage.py:24](../src/routes/session/storage.py#L24)) does two things worth
knowing: a session whose last history entry is not `SUCCESS` becomes an HTTP **502**, and the
tool calls recorded *since this turn's starting index* are scanned for mutation tool names and
returned as a `mutations[]` list so the frontend can refresh the affected paths.

Sessions live only in process memory — no persistence, and no multi-worker deployment.

### Flow B — a background task

```
ChatAgent ──tool──> start_background_task(description)     engine/jobs.py
                      ├─ TaskJob into _jobs registry (uuid12, status="running")
                      ├─ threading.Thread(daemon=True) ──> _run_job
                      └─ returns "…task_id: abc123…" IMMEDIATELY (chat is never blocked)

_run_job: build_task_input(task_id, description)   # task + ai_map
          run_agent_session(TaskAgent, …, rotated model)
          job.status = "done" | "error";  job.session = session

TaskAgent ──tool──> update_plan(task_id, steps) ──> _jobs[task_id].plan = steps
ChatAgent ──tool──> check_task_status(task_id)  ──> status + rendered plan + final summary
```

The point of the registry is that `check_task_status` reads **plain state**: a progress query
costs no LLM call at all. `_format_plan` renders the steps as `[ ] / [~] / [x]`.

Note the deliberate circular-import break: `jobs.py` imports `task_agent` *inside* the functions
([jobs.py:53](../src/agentic/engine/jobs.py#L53), [jobs.py:80](../src/agentic/engine/jobs.py#L80)),
because the cycle would otherwise be engine → agents → tools → engine. The same trick appears in
`tools/delegation.py` for `ask_librarian`.

### Flow C — the summarisation pipeline

This is the only flow that starts outside the API, and the only one that *writes* the navigation
layer the agents later read.

```
file saved in the vault
  └─ watchdog MarkdownHandler            main.py          + SSE broadcast to the frontend
       └─ SummaryScheduler.schedule()     core/scheduler.py
            · skipped when has_content_changed() is False  ← breaks the write-back loop
            · 30-min debounce per file; a new save resets the timer
       └─ (timer fires) process_obsidian_file()            core/obsidian_processor.py
            ├─ run_agent_session(SummarizerAgent)     ← engine, toolless
            ├─ update_vault_data(): ai_summary + content_hash + linked_files → frontmatter,
            │                        filemap_summary → .ai_map.json
            └─ process_folder_summary(parent)
                 ├─ run_agent_session(FolderSummarizerAgent)
                 ├─ update_folder_data(): .index.md frontmatter + file list, dir entry in .ai_map.json
                 └─ returns changed?  ──> FolderSummaryScheduler.schedule(grandparent)
                                           60-min debounce, one level per step,
                                           and only while something actually changed
```

Two feedback loops have to be cut here, and both cuts are load-bearing:

- the engine writes frontmatter back into the file it just summarised, which the watchdog sees as
  a modification → `has_content_changed()` compares the body hash against the stored
  `content_hash` and ignores events where only frontmatter moved;
- a deep edit would otherwise recompute every folder up to the root → the cascade runs at double
  debounce and stops as soon as a level's summary comes back unchanged.

Three other entry points reach the same pipeline: `POST /files/summary` (summarise one note now,
synchronously), `POST /files/build-missing-summaries` (sweep the whole vault), and the
`run_ai_map_maintenance` thread ([core/map_maintenance.py](../src/core/map_maintenance.py)), which
hourly prunes orphaned map entries, refreshes each `.index.md` file list, and schedules anything
still marked "Zusammenfassung ausstehend…" with `force=True`.

### Nested sessions

A chat tool call can start a whole second engine session inside the first.
`tools/delegation.py::_ask_librarian_tool` runs `ask_librarian(question)` synchronously, then
returns the answer, the source paths, **and the full text of those sources** — so the caller never
has to spend a round re-loading them. If the librarian session failed, the tool returns a plain
error string and the chat turn continues.

Nested sessions get their own `session_id`, their own log file, and their own iteration budget.
They are invisible to the outer session except as a tool result.

---

## 9. The tool catalogue

[src/agentic/tools/](../src/agentic/tools/) — four modules by concern, all exporting `WikiTool`
instances. Their argument models live together in
[src/schemas/tool_args.py](../src/schemas/tool_args.py). `CONTENT_TOOLS` is the shared "standard
capability set" handed to both Chat and TaskAgent; everything else is attached per agent.

| Tool | Args | Backed by | Writes? |
|---|---|---|---|
| `load_files` | `PathsArgs` | `navigation.load_files` | no |
| `load_file_summaries` | `PathsArgs` | `navigation.load_file_summaries` | no |
| `load_directory_summaries` | `PathsArgs` | `navigation.load_directory_summaries` | no |
| `ask_librarian` | `AskLibrarianArgs` | nested Librarian session | no |
| `web_search` | `WebSearchArgs` | `agents.web_search` (Search Grounding) | no |
| `deep_reasoning` | `ReasoningArgs` | `agents.reasoner` (Antigravity) | no |
| `create_directory` | `CreateDirectoryArgs` | `navigation.create_directory` | **yes** |
| `create_file` | `CreateFileArgs` | `navigation.create_file` | **yes** |
| `edit_file` | `EditFileArgs` | `navigation.edit_file` | **yes** |
| `move_file` | `MoveFileArgs` | `navigation.move_file` | **yes** |
| `delete_file` | `DeleteFileArgs` | `navigation.delete_file` | **yes** |
| `start_background_task` | `StartBackgroundTaskArgs` | `engine.jobs` | — |
| `check_task_status` | `CheckTaskStatusArgs` | `engine.jobs` | — |
| `update_plan` | `UpdatePlanArgs` | `engine.jobs._update_plan` | job registry only |

Note that the read tools (`vault_read.py`) are wrapped through a tiny `_adapt()` so the
batch loaders match the `paths: list[str]` tool signature — the batching is a first-class
concern, hammered on in every prompt that uses them.

Two properties of the write tools shape the prompts around them
([src/navigation/vault_mutation.py](../src/navigation/vault_mutation.py)):

- **Tolerant path resolution.** Models rarely get a path exactly right, so existing targets go
  through the same fuzzy `_resolve` as the read side (Unicode normalisation, case, umlaut
  transliteration, root-prefix stripping like `app/data/`, then a similarity pass). Ambiguity
  returns a *candidate list* rather than a guess. New paths get normalisation and an escape-the-
  vault check only — there is nothing to match against.
- **Refusal over damage.** Existing targets are never silently overwritten (except by `edit_file`,
  whose job is exactly that), and every failure comes back as a `"Fehler: …"` string. Both agent
  prompts therefore instruct: report the error to the user, do not quietly retry a variant.

`edit_file` preserves the YAML frontmatter and strips any frontmatter the model included in its
`content` — otherwise a model that copied a whole file as a template would double it up.

---

## 10. Logging, threads, and state

**Session logs.** [engine/session_log.py](../src/agentic/engine/session_log.py) writes one
Markdown file per session to `logs/llm_details/<ts>_<agent>_<sessionid>.md`, appended after each
step so a crash mid-loop still leaves everything up to that point on disk. Each step records the
*complete context as sent*, the raw response, token counts, and tool calls with results;
compaction and turn-end tallies get their own sections. A chat session that spans many messages
stays one file (via `existing_path`). The directory is capped at 100 files, oldest pruned.

**Threads in play.** Started in [main.py](../src/main.py): the watchdog observer, the git backup
loop, and the ai-map maintenance loop (all daemon). Plus: one `threading.Timer` per pending
summary and per pending folder cascade, one thread per background task, and FastAPI's thread pool
for the sync routes.

**Shared mutable state, and its lock.**

| State | Lock | Lives in |
|---|---|---|
| `_sessions` (chat sessions) | `_sessions_lock` | routes/session/storage.py |
| `_jobs` (task registry) | `_jobs_lock` | engine/jobs.py |
| model rotation cycles | `_rotation_lock` (one per module) | librarian.py, task_agent.py |
| pending summary / cascade timers | per-scheduler `_lock` | core/scheduler.py |

All of it is in-process and in-memory. Restart loses chat sessions and background jobs; running
more than one worker would give each worker its own copy of everything in that table.

---

## 11. Rough edges and transitional state

Worth knowing before you touch something, in rough order of how likely it is to bite:

- **Circular imports are managed by hand.** engine → agents → tools → engine is a real cycle,
  broken in two places by function-local imports (`jobs.py` → `task_agent` for `TaskAgent` and
  `build_task_input`, `delegation.py` → `librarian`) and by `obsidian_processor.py` importing the
  engine inside its process functions. A new cross-layer import is the most likely way to break
  startup.
- **`task_agent.py` is still the public face of the background-task flow**, but it no longer owns
  it: the registry lives in [engine/jobs.py](../src/agentic/engine/jobs.py) and the rotation in
  [engine/model_rotation.py](../src/agentic/engine/model_rotation.py). The module itself is now
  just the agent definition plus `build_task_input`.
- **`runner._strip_json_fence`** is a module-level alias for the function now in `response.py`,
  kept so existing call sites and tests resolve.
- **Chat's budget is 4 iterations, i.e. 3 real tool rounds** before the forced-answer nudge.
  Anything needing a fourth is supposed to become a background task. Changing the number changes
  how often that handoff happens.
- **An API error ends the turn immediately** — no engine-level retry beyond litellm's fallback
  chain. For a chat request that surfaces as a 502.
- **Retries grow the context.** Each invalid final answer appends the raw bad response *and* the
  error report. With a large `max_retries` and a model that keeps missing the schema, the context
  inflates fast; compaction does not run on this path (only after tool rounds).
- **`is_successful` only inspects the last history entry.** A session that errored five times and
  then succeeded reads as successful — correct for the API, but it means `history` is the only
  place where a turn's real cost is visible.
- **`core/core_engine.py` is a second, older implementation** of hashing, `.index.md` creation and
  map updating, separate from `obsidian_processor.py`. Only `ensure_directory_index` and
  `update_ai_map` are still used (by `rebuild.py` and `build-missing-summaries`); its
  `process_document` is dead. Don't extend it — `ObsidianVaultManager` is the live path.
- **Prompts are German and world-building-specific.** They are not a thin veneer: the guards match
  German keywords, and the response-format instructions come from German field descriptions. A
  language change is a cross-cutting change, not a prompt swap.

---

## 12. Recipes

**Add a tool.** Define the args model in [src/schemas/tool_args.py](../src/schemas/tool_args.py),
add the `WikiTool` to the right module in
`src/agentic/tools/` (read / write / delegation / tasks), export it from `tools/__init__.py`, and
either add it to `CONTENT_TOOLS` (if Chat *and* TaskAgent should have it) or attach it to one
agent's `tools=[…]`. Then describe it in that agent's system prompt — the schema description alone
is rarely enough steering. If it mutates the vault, add its name to `MUTATION_TOOL_NAMES`
(for the guard) and to the mutation set in `routes/session/storage.py` (for the frontend).

**Add an engine agent.** Input/output models in `src/schemas/`, then a `WikiAgent` in
`src/agentic/agents/`, then drive it with `run_agent_session`. Give it compaction only if it will
run many rounds; give it `require_tool_call_first_round` only if its prompt genuinely mandates a
first tool call.

**Expose an agent to the Chat agent.** Write a thin `WikiTool` in `tools/delegation.py` whose
`func` runs the nested session and flattens the result (plus any supporting material) into one
string — `_ask_librarian_tool` is the pattern, including the lazy import.

**Debug a run.** Open the session's file in `logs/llm_details/`. It has the exact context per
step, so a misbehaving loop usually explains itself: look for a missing tool result, a compaction
boundary, or the forced-final-answer instruction arriving earlier than you expected.
