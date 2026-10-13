# src/navigation/vault_navigation.py
"""Navigation tools for the librarian agent.

What is returned is always the full vault path, i.e. the path relative to the
data directory (e.g. "Reference/Glossary/Terms and Abbreviations.md").
What is accepted, by contrast, is deliberately much more permissive: a path does
not have to match exactly for a call to succeed (see _resolve). An agent can
therefore work with a bare file name, different capitalization or an incomplete
path, and gets the canonical path back in the response to keep navigating with.
"""
import difflib
import json
import os
import unicodedata
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from src.core.obsidian_processor import FRONTMATTER_PATTERN, PENDING_SUMMARY_TEXT, is_summarizable_path
from src.core.logging_config import logger

VAULT_ROOT = Path(os.getenv("WATCH_DIR") or os.getenv("VAULT_PATH") or ("/app/data" if os.path.exists("/app/data") else "./data.example")).resolve()

# Vault root identifiers an agent might prepend to a path
# ("/app/data/Reference", "data/Reference", "./vault/Reference", ...)
ROOT_ALIASES = {"app", "data", "data.example", "vault", "wiki", "obsidian"}

# How many alternatives to list when the input is ambiguous
MAX_SUGGESTIONS = 8

# Umlaut transliterations (ä -> ae), so that an ASCII spelling such as
# "Jahresuebersicht" finds the folder "Jahresübersicht". casefold() already covers ß.
UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "æ": "ae", "ø": "oe", "å": "aa"})

# The similarity above which a name counts as a typo match (final search stage)
TYPO_THRESHOLD = 0.8


class VaultPathError(ValueError):
    """A path could not be resolved (unambiguously) within the vault.

    For ambiguous input, 'candidates' holds the possible vault paths.
    """

    def __init__(self, message: str, candidates: list[str] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


def _vault_root(vault_root: Path | None = None) -> Path:
    return Path(vault_root) if vault_root else VAULT_ROOT


def _norm(text: str) -> str:
    """Normalizes spelling for comparison: Unicode normal form (important for
    umlauts, which land in the filesystem as NFC or NFD depending on the sync
    source), slash direction, capitalization and surrounding slashes."""
    text = unicodedata.normalize("NFC", str(text)).replace("\\", "/").strip()
    return text.strip("/").casefold()


def _fold(text: str) -> str:
    """Like _norm, additionally without umlauts and accents ("Jahresübersicht" ->
    "jahresuebersicht"), so that ASCII transliterations of a name match too."""
    folded = _norm(text).translate(UMLAUT_MAP)
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _vault_path(target: Path, vault_root: Path | None = None) -> str:
    """Full path relative to the data directory, in POSIX notation."""
    root = _vault_root(vault_root).resolve()
    rel = target.resolve().relative_to(root).as_posix()
    return rel if rel != "." else ""


def _candidate_paths(root: Path, expect: str | None) -> list[Path]:
    """All eligible vault entries (folders or Markdown files)."""
    candidates: list[Path] = []
    if expect != "file":
        candidates.append(root)
    for entry in root.rglob("*"):
        if ".git" in entry.parts:
            continue
        if entry.is_dir():
            if expect != "file":
                candidates.append(entry)
        elif entry.suffix == ".md" and expect != "dir":
            # Explicitly requested .index.md/.ai_map neighbours are reachable via
            # the direct path; only real notes count for the search.
            if is_summarizable_path(entry):
                candidates.append(entry)
    return candidates


def _strip_root_prefix(segments: list[str]) -> list[str]:
    """Removes leading root identifiers such as "app/data/" or "data/"."""
    while len(segments) > 1 and _norm(segments[0]) in ROOT_ALIASES:
        segments = segments[1:]
    return segments


def _fuzzy_resolve(raw: str, root: Path, expect: str | None) -> Path:
    """Finds the matching vault entry when the path does not exist literally.

    Staged from strict to tolerant; the first stage with exactly one hit wins.
    Multiple hits report the alternatives so the agent can narrow things down
    instead of silently getting the wrong file.
    """
    segments = _strip_root_prefix([s for s in _norm(raw).split("/") if s not in ("", ".")])
    if not segments:
        return root

    needle = "/".join(segments)
    tail = segments[-1]
    tail_stem = tail[:-3] if tail.endswith(".md") else tail
    # Search terms with and without the .md suffix, each normalized and umlaut-folded
    needles = {needle, f"{needle}.md"} if not needle.endswith(".md") else {needle, needle[:-3]}
    needles_folded = {_fold(n) for n in needles}
    tail_folded = _fold(tail_stem)

    entries = [
        (c, _norm(vp), _norm(c.stem), _fold(vp), _fold(c.stem))
        for c in _candidate_paths(root, expect)
        for vp in [_vault_path(c, root)]
    ]

    stages = [
        # 1. full path, with the .md suffix optionally added or removed
        lambda vp, stem, vp_f, stem_f: vp in needles,
        # 2. path tail: "Glossary/Terms..." finds the entry below it
        lambda vp, stem, vp_f, stem_f: any(vp.endswith(f"/{n}") for n in needles),
        # 3. bare name/stem: "Terms and Abbreviations"
        lambda vp, stem, vp_f, stem_f: stem == tail_stem,
        # 4. like 1-3, but umlaut-folded: "technologie/militaertechnik"
        lambda vp, stem, vp_f, stem_f: (
            vp_f in needles_folded
            or any(vp_f.endswith(f"/{n}") for n in needles_folded)
            or stem_f == tail_folded
        ),
        # 5. substring in the name: "Terms"
        lambda vp, stem, vp_f, stem_f: tail_stem in stem or tail_folded in stem_f,
        # 6. substring anywhere in the path
        lambda vp, stem, vp_f, stem_f: needle in vp or tail_folded in vp_f,
    ]

    for matches_stage in stages:
        hits = [c for c, *fields in entries if matches_stage(*fields)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise _ambiguous(raw, hits, root)

    # 7. final stage: catch typos in the name via similarity
    scored = [
        (difflib.SequenceMatcher(None, tail_folded, stem_f).ratio(), c)
        for c, vp, stem, vp_f, stem_f in entries
    ]
    best = max(scored, key=lambda s: s[0], default=(0.0, None))
    if best[0] >= TYPO_THRESHOLD:
        near_best = [c for score, c in scored if score >= best[0] - 0.01]
        if len(near_best) > 1:
            raise _ambiguous(raw, near_best, root)
        return best[1]

    kind = {"dir": "No folder", "file": "No file"}.get(expect, "No entry")
    raise VaultPathError(
        f"{kind} matching '{raw}' found in the vault. "
        f"load_ai_map() lists all existing paths."
    )


def _ambiguous(raw: str, hits: list[Path], root: Path) -> VaultPathError:
    """Error with a list of options, so the agent can narrow things down instead
    of silently getting the wrong entry."""
    options = sorted(_vault_path(h, root) or "(vault root)" for h in hits)
    shown = ", ".join(f"'{o}'" for o in options[:MAX_SUGGESTIONS])
    more = f" (+{len(options) - MAX_SUGGESTIONS} more)" if len(options) > MAX_SUGGESTIONS else ""
    return VaultPathError(
        f"'{raw}' is ambiguous. It could mean: {shown}{more}. "
        f"Please ask again using the full vault path.",
        candidates=options,
    )


def _direct_path(raw: str, root: Path) -> Path | None:
    """Literal resolution: vault path, leading slash, backslashes or an absolute
    path inside the vault. Returns None if that does not hit anything existing
    inside the vault - paths leading outside ("../../etc/passwd") are discarded
    here and never show up in the fuzzy search either."""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / raw.lstrip("/")

    try:
        resolved = candidate.resolve()
    except OSError:
        return None

    if resolved != root and root not in resolved.parents:
        return None
    return resolved if resolved.exists() else None


def _resolve(path: str | Path, vault_root: Path | None = None, expect: str | None = None) -> Path:
    """Resolves a path specification into a real path on the filesystem.

    First literally (see _direct_path); if that hits nothing suitable,
    _fuzzy_resolve takes over with the tolerant search (partial path, bare file
    name, different capitalization, missing .md suffix, umlaut transliteration,
    typos).

    'expect' restricts to "dir" or "file" and makes the search more accurate.
    The result is always an existing entry inside the vault.
    """
    root = _vault_root(vault_root).resolve()
    raw = unicodedata.normalize("NFC", str(path)).replace("\\", "/").strip()

    if raw.strip("/") in ("", "."):
        if expect == "file":
            raise VaultPathError("A file requires a path, not the vault root.")
        return root

    direct = _direct_path(raw, root)
    if direct is not None:
        if direct.is_dir() and expect != "file":
            return direct
        if direct.is_file() and expect != "dir":
            return direct

    target = _fuzzy_resolve(raw, root, expect)
    logger.info(f"[Navigation] Path '{path}' resolved to '{_vault_path(target, root)}'")
    return target


def _resolve_any(path: str | Path, vault_root: Path | None = None, prefer: str = "file") -> Path:
    """Like _resolve, but without a fixed expectation: a literally existing path
    always wins (even if it is the other type), then the preferred type is
    searched for, and only last the other one. That way the folder "Reference"
    beats the file "Reference Architecture Notes.md", while a bare file name is
    still found.
    """
    root = _vault_root(vault_root).resolve()
    raw = unicodedata.normalize("NFC", str(path)).replace("\\", "/").strip()

    if raw.strip("/") in ("", "."):
        return root

    direct = _direct_path(raw, root)
    if direct is not None:
        return direct

    other = "dir" if prefer == "file" else "file"
    try:
        return _resolve(path, root, expect=prefer)
    except VaultPathError as prefer_error:
        try:
            return _resolve(path, root, expect=other)
        except VaultPathError as other_error:
            # A list of options helps the agent more than a bare "not found".
            raise other_error if other_error.candidates else prefer_error


def _read_md(filepath: Path) -> tuple[dict, str]:
    """Reads a Markdown file and separates frontmatter from content."""
    if not filepath.exists():
        return {}, ""

    content = filepath.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}, content.strip()

    try:
        return yaml.safe_load(match.group(1)) or {}, match.group(2).strip()
    except yaml.YAMLError as e:
        logger.error(f"[Navigation] YAML parse error in {filepath}: {e}")
        return {}, content.strip()


def _strip_frontmatter(text: str) -> str:
    """Removes any YAML frontmatter (---...---) from the beginning of a text and
    returns only the content below it. A no-op if there is none. Also applied
    defensively to agent input (see vault_mutation.edit_file), so that stale
    frontmatter sent along by accident does not end up duplicated."""
    match = FRONTMATTER_PATTERN.match(text)
    return match.group(2).strip() if match else text.strip()


def load_ai_map(vault_root: Path | None = None) -> dict:
    """Returns the contents of the central .ai_map.json.

    Structure: {"directories": {vault_path: short_summary}, "files": {vault_path: short_summary}}
    """
    ai_map_path = _vault_root(vault_root) / ".ai_map.json"
    if not ai_map_path.exists():
        logger.error(f"[Navigation] .ai_map.json not found: {ai_map_path}")
        return {"directories": {}, "files": {}}

    try:
        with open(ai_map_path, "r", encoding="utf-8") as f:
            ai_map = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"[Navigation] .ai_map.json is invalid: {e}")
        return {"directories": {}, "files": {}}

    ai_map.setdefault("directories", {})
    ai_map.setdefault("files", {})
    return ai_map


def load_directory_summary(path: str | Path, vault_root: Path | None = None) -> str:
    """Returns the detailed summary of a folder (the ai_summary of its .index.md)
    together with the short summaries of all contained files and subfolders.
    Every line names the full vault path of the entry.

    The path does not have to match exactly (see _resolve); if it points at a
    file, that file's folder is returned.
    """
    root = _vault_root(vault_root)
    hint = ""
    try:
        target = _resolve_any(path, root, prefer="dir")
    except VaultPathError as e:
        return f"Error: {e}"

    # If the input points at a file, the folder above it is the most useful answer.
    folder = target if target.is_dir() else target.parent
    if not target.is_dir():
        hint = f"> Note: '{path}' is the file '{_vault_path(target, root)}' — its folder is shown below.\n"

    ai_map = load_ai_map(root)
    files_map = ai_map["files"]
    dirs_map = ai_map["directories"]

    index_fm, _ = _read_md(folder / ".index.md")
    folder_label = _vault_path(folder, root) or "(vault root)"

    sections = [
        f"{hint}# Folder: {folder_label}",
        "",
        "## Summary",
        index_fm.get("ai_summary", PENDING_SUMMARY_TEXT),
    ]

    file_lines = []
    dir_lines = []
    for entry in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        entry_path = _vault_path(entry, root)
        if entry.is_dir():
            sub_fm, _ = _read_md(entry / ".index.md")
            summary = sub_fm.get("ai_summary") or dirs_map.get(entry_path, PENDING_SUMMARY_TEXT)
            dir_lines.append(f"- `{entry_path}/` — {summary}")
        elif is_summarizable_path(entry):
            summary = files_map.get(entry_path, PENDING_SUMMARY_TEXT)
            file_lines.append(f"- `{entry_path}` — {summary}")

    sections += ["", "## Files in this folder"]
    sections += file_lines or ["(none)"]
    sections += ["", "## Subfolders"]
    sections += dir_lines or ["(none)"]

    return "\n".join(sections)


def load_file_summary(path: str | Path, vault_root: Path | None = None) -> str:
    """Returns a file's ai_summary (from its YAML frontmatter).

    The path does not have to match exactly (see _resolve); if it points at a
    folder, that folder's summary from .index.md is returned.
    """
    root = _vault_root(vault_root)
    try:
        target = _resolve_any(path, root, prefer="file")
    except VaultPathError as e:
        return f"Error: {e}"

    if target.is_dir():
        target = target / ".index.md"

    fm, _ = _read_md(target)
    return fm.get("ai_summary") or PENDING_SUMMARY_TEXT


def load_file(path: str | Path, vault_root: Path | None = None) -> str:
    """Loads a file's content from the vault WITHOUT the YAML frontmatter - that is
    only relevant for load_file_summary/load_directory_summary, not for the actual
    document content (and in particular must not be passed back to edit_file
    unfiltered, or the frontmatter would be duplicated on the next write).

    The path does not have to match exactly (see _resolve); if it points at a
    folder, the content of its .index.md is returned.
    """
    root = _vault_root(vault_root)
    try:
        filepath = _resolve_any(path, root, prefer="file")
    except VaultPathError as e:
        return f"Error: {e}"

    if filepath.is_dir():
        filepath = filepath / ".index.md"
        if not filepath.is_file():
            return f"Error: folder '{path}' does not have an .index.md yet."

    _, content = _read_md(filepath)
    return content


def _batch(paths: list[str], loader) -> str:
    """Applies one of the load_* functions to several paths and joins the results
    with a separator line per path, so that a single tool call can return several
    folders/files at once instead of querying them one after another."""
    if not paths:
        return "Error: no paths provided."
    return "\n\n".join(f"===== Requested: '{p}' =====\n{loader(p)}" for p in paths)


def format_ai_map(ai_map: dict[str, dict[str, str]]) -> str:
    """Formats the result of load_ai_map() as a compact Markdown overview of all
    folders and files with their short summaries - the usual research starting
    point that agents get in their context from the outset (see Librarian, Chat)."""
    lines = ["## Folders", ""]
    lines += [f"- `{path}/` — {summary}" for path, summary in sorted(ai_map["directories"].items())] or ["(none)"]
    lines += ["", "## Files", ""]
    lines += [f"- `{path}` — {summary}" for path, summary in sorted(ai_map["files"].items())] or ["(none)"]
    return "\n".join(lines)


def load_directory_summaries(paths: list[str], vault_root: Path | None = None) -> str:
    """Like load_directory_summary, but for several folders in one call."""
    return _batch(paths, lambda p: load_directory_summary(p, vault_root))


def load_file_summaries(paths: list[str], vault_root: Path | None = None) -> str:
    """Like load_file_summary, but for several files in one call."""
    return _batch(paths, lambda p: load_file_summary(p, vault_root))


def load_files(paths: list[str], vault_root: Path | None = None) -> str:
    """Like load_file, but for several files in one call."""
    return _batch(paths, lambda p: load_file(p, vault_root))
