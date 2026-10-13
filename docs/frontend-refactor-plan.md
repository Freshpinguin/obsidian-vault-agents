# Frontend Refactor Plan — split `index.html` into static files

**Status:** not started
**Target:** `index.html` (3040 lines) → `index.html` (~380 lines) + `static/css/*` + `static/js/*`
**Written for:** the engineer or agent executing this refactor. You do not need prior context on this repo.

---

## 1. Context

`index.html` sits at the repo root and is served as a single self-contained file by
`src/routes/frontend/get_frontend.py` (`FileResponse` on `GET /`). It is a vanilla-JS
single-page app that talks to the FastAPI JSON API in `src/routes/`.

It has three blocks:

| Block | Lines | Size |
|---|---|---|
| `<style>` | 16–1463 (content 17–1462) | ~1450 lines |
| markup (`<body>`) | 1465–1835 | ~370 lines |
| `<script>` | 1836–3038 (content 1837–3037) | ~1200 lines |

Both the CSS and the JS are **already divided by comment headers** (the JS blocks are even
numbered 1–11). This refactor is therefore a cut-and-paste job along boundaries that already
exist — not a rewrite. Do not take it as licence to redesign anything.

## 2. Goal

Physically split the file so that each concern lives in its own file, with **no build step and
no new runtime dependency**. Use native ES modules (`<script type="module">`) and plain
`<link>` tags, served by FastAPI's `StaticFiles`.

### Explicitly rejected approaches — do not propose or introduce these

- **React / Vue / Svelte / any npm toolchain or bundler.** The owner does not want it.
- **Jinja2 templating** (even though `Jinja2==3.1.6` is already in `src/requirements.txt`).
  It would only help the markup third — the smallest and least problematic part — and does
  nothing for the CSS or JS, which are 88% of the file.
- **HTMX** or any approach that makes FastAPI return HTML fragments. The backend is cleanly
  JSON-API with schemas (`src/schemas/`) and route tests (`src/tests/routes/`). Do not touch
  that boundary.
- **NiceGUI / Reflex / Streamlit.** Full rewrite of a working UI.

## 3. Hard constraints

1. **Zero visual change.** The UI must be pixel-identical when you are done. Preserve CSS rule
   order exactly (see §5) — the stylesheet relies on source order for cascade ties.
2. **Zero behaviour change.** No new features, no bug fixes, no renames of DOM ids or CSS
   classes, no changes to API request/response shapes.
3. **No backend API change.** The only backend edit in this plan is mounting `StaticFiles`
   and (optionally) a cache header. `src/routes/files/`, `src/routes/session/` and all schemas
   stay untouched.
4. **No reformatting.** When moving code, do not reindent, reorder, rename, or "tidy" it. The
   one permitted whitespace change is a uniform 2-space dedent per file (the code is currently
   indented inside `<style>` / the IIFE). Keeping diffs mechanical is what makes this reviewable.
5. **Comments stay German.** This codebase comments in German. Preserve every existing comment
   verbatim and write any new comment in German to match.
6. **Branch first.** Current branch is `main`. Create a branch, e.g. `refactor/frontend-split`.
   Note the working tree already has unrelated uncommitted changes — do not commit those; stage
   only the files this plan touches.

## 4. Target layout

```
index.html                  # markup only + <link>/<script type="module"> tags
static/
  css/
    tokens.css
    shell.css
    nav.css
    panes.css
    explorer.css
    viewer.css
    editor.css
    chat.css
    components.css
    modals.css
    utilities.css
  js/
    state.js
    dom.js
    api.js
    markdown.js
    toast.js
    tree.js
    viewer.js
    editor.js
    summaries.js
    chat.js
    panes.js
    live.js
    settings.js
    main.js
  vendor/
    marked.min.js
```

`static/` goes at the repo root, next to `index.html`.

---

## 5. Phase 1 — CSS extraction

Largest chunk, lowest risk, independently verifiable. **Do this first and stop to verify before
touching any JS.**

Split the content of the `<style>` block (lines 17–1462) into the files below. Every range is
**contiguous and in original order** — this is deliberate, so that concatenating the files in
link order reproduces the original stylesheet byte-for-byte (modulo indentation). Do not
regroup rules across ranges even where a rule looks misfiled.

| # | File | Source lines | Contains |
|---|---|---|---|
| 1 | `tokens.css` | 17–73 | `:root` custom properties, `*` reset, `html, body`, custom scrollbars |
| 2 | `shell.css` | 74–81 | App Shell Layout |
| 3 | `nav.css` | 82–192 | Top Navigation Bar (incl. `@keyframes pulse` at 147) |
| 4 | `panes.css` | 193–210 | Main 3-Column Workspace, Pane Bases |
| 5 | `explorer.css` | 211–411 | LEFT PANE: File Explorer, Tree Nodes, Resizer Bars |
| 6 | `viewer.css` | 412–754 | CENTER PANE, Empty Welcome State, File Content Display, AI Summary Box, Wikilinks & Relations, Markdown Rendered Typography, Inline Wikilinks |
| 7 | `editor.css` | 755–873 | Raw Source View & Interactive Editor |
| 8 | `chat.css` | 874–1144 | RIGHT PANE: Chat Assistant, Thinking Animation, Chat Input Footer |
| 9 | `components.css` | 1145–1224 | Toast Notifications, Button Spinner |
| 10 | `modals.css` | 1225–1443 | Settings/Optionen Modal & Toggles, iOS Style Switch, Floating Settings Button |
| 11 | `utilities.css` | 1444–1462 | Body toggle helper classes, Editor font size classes (incl. `@keyframes spin`) |

These ranges have been verified mechanically: concatenating them in table order reproduces
lines 17–1462 of the current `index.html` with an empty diff. If your split produces a diff,
the error is yours, not the table's.

Then replace lines 16–1463 of `index.html` (the whole `<style>` element) with eleven `<link>`
tags **in exactly the table order**:

```html
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/css/shell.css">
<link rel="stylesheet" href="/static/css/nav.css">
<link rel="stylesheet" href="/static/css/panes.css">
<link rel="stylesheet" href="/static/css/explorer.css">
<link rel="stylesheet" href="/static/css/viewer.css">
<link rel="stylesheet" href="/static/css/editor.css">
<link rel="stylesheet" href="/static/css/chat.css">
<link rel="stylesheet" href="/static/css/components.css">
<link rel="stylesheet" href="/static/css/modals.css">
<link rel="stylesheet" href="/static/css/utilities.css">
```

### Do not use `@import`

A single stylesheet with eleven `@import` rules serializes the downloads and produces a visible
flash of unstyled content. Eleven `<link>` tags over a local connection cost nothing.

### Phase 1 verification

Mechanical, before any browser check. From the repo root, with the original file available as
`git show HEAD:index.html`:

```sh
# extract the original style block
git show HEAD:index.html | sed -n '17,1462p' | sed 's/^  //' > /tmp/css-before.txt

# concatenate the split files in link order
for f in tokens shell nav panes explorer viewer editor chat components modals utilities; do
  cat static/css/$f.css
done > /tmp/css-after.txt

diff /tmp/css-before.txt /tmp/css-after.txt
```

The diff must be empty (allow only trailing-newline differences at file joins; if the join
newlines bother the diff, compare with `diff <(tr -s '\n' < ...) ...`). If it is not empty, you
dropped or duplicated a rule — fix it before continuing.

Then load the app and confirm visually: all three panes, the tree, an open note, the editor, the
chat pane, both modals, a toast. **Commit here.**

---

## 6. Phase 2 — serve the static directory

### `src/main.py`

Add the mount after the existing `app.include_router(api_router)` on line 24. `StaticFiles`
must be mounted on the `FastAPI` app, not on an `APIRouter` (routers cannot mount).

```python
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parents[1]   # Repo-Wurzel
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
```

Note `src/main.py` already imports `Path` (line 4). The mount at `/static` does not shadow the
existing `GET /` route.

### `src/routes/frontend/get_frontend.py`

Leave the route as-is. The existing `FRONTEND_PATH = parents[3] / "index.html"` still resolves
to the repo root, and `index.html` does not move.

Recommended one-line addition while you are in the file — without it you will spend the rest of
this refactor hard-refreshing:

```python
return FileResponse(FRONTEND_PATH, headers={"Cache-Control": "no-cache"})
```

### Phase 2 verification

`pytest` must still pass (there are no frontend tests, but there are route tests in
`src/tests/routes/`). Confirm `GET /static/css/tokens.css` returns 200. **Commit here.**

---

## 7. Phase 3 — JS extraction

The `<script>` block is one IIFE: `(() => {` on line 1837, `})();` on line 3037. **Both lines
get deleted** — ES modules have their own scope, so the wrapper is redundant.

Extract in the order of the table (leaf modules first), verifying in the browser after each
module. The source ranges below are exhaustive and non-overlapping — verified mechanically:
every line from 1838 to 3035 is accounted for, with the single exception of lines 1915–1916,
which are two blank separator lines and can be dropped.

| Order | File | Source lines | Contents |
|---|---|---|---|
| 1 | `state.js` | 1838–1846, plus the flags at 1906, 1907, 1914 | `sessionId`, `isSending`, `currentFile`, `currentFileRawContent`, `currentFileAiSummary`, `viewMode`, `vaultTreeData`, `expandedFolders`, `isSavingFile`, `isDeletingFile`, `isRequestingSummary` |
| 2 | `dom.js` | 1848–1914 (minus the three flags above) | the ~50 cached `getElementById` refs |
| 3 | `markdown.js` | 1917–1945 (§1) | `renderMarkdown`, `escapeHtml` |
| 4 | `api.js` | — (new file, see §7.3) | every `fetch` call, extracted from its call sites |
| 5 | `toast.js` | 2422–2441 | `showToast` |
| 6 | `tree.js` | 1946–2101 (§2) + 2505–2533 (§5) | `loadFileTree`, `renderTree`, `buildTreeDOM`, `renderQuickCards`, `ensureFolderVisibleInTree` (move it here from §3), explorer search filter + expand/collapse/refresh listeners |
| 7 | `viewer.js` | 2102–2214 (§3) | `loadFileContent`, breadcrumbs, tags, AI summary box, wikilink chips, chat context pill |
| 8 | `editor.js` | 2215–2421 (§4) | `checkEditorDirty`, view-mode switch, editor input/Tab handling, `saveCurrentFile`, Cmd/Ctrl+S, `openDeleteModal`, `closeDeleteModal`, delete confirmation |
| 9 | `summaries.js` | 2442–2504 + 2994–3027 | `requestSummary` (single file) and "fehlende Zusammenfassungen erstellen" (bulk) |
| 10 | `chat.js` | 2545–2712 (§7) | `addChatMessage`, `autoResizeTextarea`, `sendChatMessage`, form/Enter/new-chat listeners |
| 11 | `panes.js` | 2534–2544 (§6) + 2713–2751 (§8) | explorer/chat pane toggles, `setupResizer` and its instantiation |
| 12 | `live.js` | 2752–2814 (§9) | `scheduleFileTreeRefresh`, `initFileWatcherEvents`, the `EventSource("/files/events")` wiring |
| 13 | `settings.js` | 2815–2993 (§10) | `SETTINGS_KEY`, `defaultSettings`, `currentSettings`, `loadSettings`, `saveSettings`, `applySettings`, `openSettingsModal`, `closeSettingsModal`, option listeners, the global close-button/backdrop click delegation at 2922 |
| 14 | `main.js` | 3028–3035 (§11) | imports everything, then `loadSettings(); loadFileTree(); if (currentSettings.liveSyncEnabled) initFileWatcherEvents();` |

Then replace the `<script>` block in `index.html` with a single tag:

```html
<script type="module" src="/static/js/main.js"></script>
```

### 7.1 `state.js` must export a mutable object, not bare `let`

This is the one thing that will definitely bite you. ES module import bindings are **read-only
for the importer** — `import { currentFile } from './state.js'` followed by `currentFile = x` is
a `SyntaxError`, and the current code reassigns every one of these variables from several
sections. Export a single object instead:

```js
// Globaler Anwendungszustand
export const state = {
  sessionId: null,
  isSending: false,
  currentFile: null,
  currentFileRawContent: "",
  currentFileAiSummary: "",
  viewMode: "rendered",      // 'rendered' oder 'raw'
  vaultTreeData: null,
  expandedFolders: new Set(),
  isSavingFile: false,
  isDeletingFile: false,
  isRequestingSummary: false,
};
```

Call sites become `state.currentFile` etc. This is a find-and-replace across the extracted
modules; be systematic, and grep for each of the eleven names afterwards to confirm none is left
unqualified.

### 7.2 Circular imports are acceptable here — with one rule

`tree.js` needs `loadFileContent` from `viewer.js`, and `viewer.js` needs `renderTree` /
`ensureFolderVisibleInTree` from `tree.js`. That cycle is **fine** in ESM: function declarations
are hoisted, and the binding is resolved when the function is *called*, not when the module is
evaluated. All of these are called from event handlers.

**The rule: never call an imported function at module top level.** Only declarations, listener
registrations and constants at top level. If you find you need a top-level cross-module call,
move it into `main.js` instead.

(A tiny `bus.js` pub/sub would decouple this more cleanly. It is optional and explicitly *not*
required — direct imports keep the diff smaller and the control flow easier to follow.)

### 7.3 `api.js`

Collect every network call into one module. Current call sites:

| Source line | Call | Suggested export |
|---|---|---|
| 1951 | `GET /files` | `fetchFileTree()` |
| 2112 | `GET /files/content?path=…` | `fetchFileContent(path)` |
| 2289 | `PUT /files/content` | `saveFileContent(path, content)` |
| 2371 | `DELETE /files/content?path=…` | `deleteFile(path)` |
| 2458 | `POST /files/summary` | `requestFileSummary(path)` |
| 3005 | `POST /files/build-missing-summaries` | `buildMissingSummaries()` |
| 2609 | `POST /sessions` or `POST /sessions/{id}/messages` | `postChatMessage({ message, active_file, active_file_summary }, sessionId)` |
| 2704 | `DELETE /sessions/{id}` | `deleteSession(sessionId)` |

Keep the error handling where it currently lives (in the callers). `api.js` should do the fetch,
parse JSON, and throw on non-OK — nothing more. Do **not** change any URL, method, or payload
shape.

The `EventSource("/files/events")` at line 2781 is not a fetch; leave it in `live.js`.

### 7.4 Inline `onclick` handlers — check, then prefer removing

Four buttons in the markup use inline handlers that reach for globals:

- 1708 `btn-close-settings` → `window.closeSettingsModal && window.closeSettingsModal()`
- 1795 `btn-save-settings-close` → same
- 1808 `btn-close-delete-modal` → `window.closeDeleteModal && window.closeDeleteModal()`
- 1824 `btn-cancel-delete` → same

**Module scope is not global**, so these break unless the four `window.*` assignments at lines
2346, 2347, 2905 and 2906 are preserved verbatim in `editor.js` / `settings.js`.

There is already a "Globale Klick-Delegation für Schließen-Buttons und Backdrop" block at line
2922. **Verify whether that delegation already covers these four ids.** If it does, delete the
inline `onclick` attributes *and* the four `window.*` assignments — they are redundant. If it
does not, either add the missing `addEventListener` calls (all four buttons already have ids) or
keep the `window.*` assignments. Pick one and leave no half-state: either no inline handlers, or
inline handlers with their globals intact.

### 7.5 You do not need `DOMContentLoaded`

Module scripts are deferred by default, so `dom.js` runs after the document is parsed and every
`getElementById` resolves. Do not add a ready-wrapper, and do not add `defer` (it is implied).

### Phase 3 verification

No automated frontend tests exist, so this is a manual smoke test. After each module, and again
at the end, check the browser console is clean and that each of these works:

- [ ] tree renders; folders expand/collapse; expand-all / collapse-all / refresh
- [ ] explorer search filter
- [ ] clicking a note opens it: breadcrumbs, title, dates, tags, AI summary box, wikilink chips
- [ ] clicking an inline wikilink in rendered text navigates
- [ ] rendered ⇄ raw mode switch
- [ ] editing marks dirty; Cmd/Ctrl+S saves; save button state and status dot
- [ ] Tab key inserts in the editor rather than moving focus
- [ ] copy content button
- [ ] delete: modal opens, cancel closes, confirm deletes, toast appears
- [ ] chat: send a message, thinking indicator, response renders, wikilinks in response clickable
- [ ] chat: new-chat button clears and starts a new session
- [ ] quick-start cards on the empty state
- [ ] pane toggles (explorer, chat) and both resizer bars
- [ ] settings modal: all toggles, font size, persistence across reload (`localStorage` key `obsidian_agents_ui_settings`)
- [ ] single-file summary refresh, and bulk "fehlende Zusammenfassungen erstellen"
- [ ] live sync: touch a file in the vault on disk, confirm the tree refreshes via SSE

**Commit per module**, or at minimum one commit per table row group. Do not land all 14 modules
in one commit.

---

## 8. Phase 4 — vendor `marked` locally

Line 14 currently loads:

```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
```

Two problems: the app cannot render Markdown offline (this is a self-hosted vault tool, often on
a Raspberry Pi), and the URL is **unpinned** — `npm/marked/` resolves to whatever is latest, so
a breaking upstream release silently breaks the viewer.

Download a specific pinned version to `static/vendor/marked.min.js` and load it locally:

```html
<script src="/static/vendor/marked.min.js"></script>
```

Keep it a **classic script tag, not a module**, and keep it *before* the module script. The
existing code reads `window.marked` (lines 1930–1931) and already has a fallback path if it is
absent; leaving it as a global means `markdown.js` needs no change at all.

Record the pinned version in the commit message.

### Optional, lower priority

The Google Fonts `<link>` tags (lines 9–11) are still external, so the app does not render in its
intended typefaces offline. Vendoring Inter and JetBrains Mono is a reasonable follow-up but is
**out of scope here** — mention it, do not do it.

---

## 9. Out of scope

Do not do these as part of this refactor. Note them and move on.

- Any visual redesign or CSS cleanup (dead rules, duplicated values, consolidating the
  non-contiguous layout sections).
- Responsive layout. There are currently **no `@media` queries at all** — the app is desktop-only.
  That is a real gap and a plausible next project, but it is not this one.
- XSS hardening of `renderMarkdown`. It runs `marked` over vault content without sanitizing;
  acceptable for a single-user local tool, worth revisiting if the app is ever exposed.
- Adding a frontend test harness.
- Vendoring fonts.
- Touching anything under `src/agents/`, `src/core/`, `src/navigation/` or `src/schemas/`.

## 10. Docker: how `static/` reaches the container

The Docker setup is **separately broken** and the owner is aware of it. Context so you do not
rediscover it: `Dockerfile` copies only `src/requirements.txt` — never `src/` or `index.html` —
so the image has dependencies but no application code, and `uvicorn src.main:app` would fail with
`ModuleNotFoundError`. `docker-compose.yml` mounts only the vault. The owner develops by running
uvicorn locally, so this path has not been exercised.

**Fixing that is NOT part of this refactor.** Do not bundle it in. It is listed here only so you
know where the new `static/` directory has to be declared once the owner lands their fix.

The owner is choosing between two shapes. Check which one is in the tree when you get here:

- **Code baked into the image** (the owner's stated preference): `Dockerfile` gains
  `COPY --chown=appuser:appuser` lines for `src/`, `index.html` **and `static/`**, placed after
  `RUN useradd` and before `USER appuser`, and `--reload` is dropped from `CMD`. If these COPY
  lines exist but `static/` is missing from them, add that one line — that is in scope, because
  you created the directory.
- **Repo bind-mounted**: `docker-compose.yml` volumes gain `- .:/app`. Then `static/` needs
  nothing at all; it arrives with everything else.

If neither change has landed by the time you finish, say so in your final report and do nothing
to the Docker files.

## 11. Definition of done

- `index.html` is markup + link/script tags only, roughly 380 lines.
- The CSS concatenation diff in §5 is clean.
- Every checkbox in §7 passes in the browser with no console errors.
- `pytest` passes.
- No file under `src/` is modified except `src/main.py` (StaticFiles mount) and
  `src/routes/frontend/get_frontend.py` (cache header).
- `marked` is pinned and served locally.
- A short report naming: the commits, the §7.4 decision you made and why, and which §10 Docker
  shape you found in the tree (or that neither had landed).
