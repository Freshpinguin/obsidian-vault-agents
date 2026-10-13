# src/obsidian_processor.py
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime
import yaml  # pip install pyyaml

from src.core.logging_config import logger

# Regex for cleanly extracting the Obsidian YAML frontmatter
FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)

# Regex for Obsidian wikilinks: [[target]], [[target|label]], [[target#section|label]]
WIKILINK_PATTERN = re.compile(r"\[\[(.+?)\]\]")

# Placeholder used until a real AI summary exists. The periodic maintenance pass
# (map_maintenance) recognizes exactly this text and schedules the summary.
PENDING_SUMMARY_TEXT = "Summary pending..."


def get_content_hash(text: str) -> str:
    """Fingerprint of the document content alone (without frontmatter)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def is_summarizable_path(filepath: Path) -> bool:
    """Filters out system files (hidden, index and sync-conflict files) that should
    never be summarized in their own right."""
    name = filepath.name
    if filepath.suffix != ".md":
        return False
    if ".sync-conflict" in name:
        return False
    if name.startswith(".") or name.startswith("_"):
        return False
    if name == "CLAUDE.md":
        return False
    return True


def build_note_index(vault_root: Path) -> dict[str, str]:
    """Builds a mapping of note name -> relative path for the entire vault, so that
    wikilink targets can be resolved to real files.

    Obsidian accepts both the bare note name ([[Capybara]]) and a path ([[Animals/Capybara]]),
    so both spellings are indexed - otherwise a path-style link silently ends up in
    linked_files as an unresolvable string.
    """
    index: dict[str, str] = {}
    for md_file in vault_root.rglob("*.md"):
        if not is_summarizable_path(md_file):
            continue
        relative = md_file.relative_to(vault_root).as_posix()
        index.setdefault(md_file.stem, relative)
        index.setdefault(relative.removesuffix(".md"), relative)
    return index


def extract_linked_files(vault_root: Path, text: str) -> list[str]:
    """Extracts all Obsidian wikilinks ([[target]], [[target|text]], [[target#section]])
    from the content and resolves them, where possible, to the actual file in the vault."""
    note_index = build_note_index(vault_root)
    linked_files = []
    seen = set()

    for raw_target in WIKILINK_PATTERN.findall(text):
        target = raw_target.split("|")[0].split("#")[0].strip()
        if not target or target in seen:
            continue
        seen.add(target)
        linked_files.append(note_index.get(target, target))

    return linked_files


def build_file_map_content(vault_root: Path, folder_path: Path, ai_map: dict) -> str:
    """Builds a small Markdown list of all files in this folder (one line per file)
    with the summary currently stored for each in .ai_map.json."""
    files_map = ai_map.get("files", {})
    lines = []
    for entry in sorted(folder_path.iterdir(), key=lambda p: p.name.lower()):
        if not is_summarizable_path(entry):
            continue
        rel_path = entry.relative_to(vault_root).as_posix()
        summary = files_map.get(rel_path, PENDING_SUMMARY_TEXT)
        lines.append(f"- **{entry.name}** — {summary}")

    if not lines:
        return ""

    return "## 📂 Files in this folder\n\n" + "\n".join(lines)


class ObsidianVaultManager:
    """Encapsulates read and write access to the Obsidian vault."""

    def __init__(self, vault_root: Path):
        self.vault_root = vault_root
        self.ai_map_path = vault_root / ".ai_map.json"

    def _read_md_file(self, filepath: Path) -> tuple[dict, str]:
        """Reads a Markdown file and separates frontmatter from content."""
        if not filepath.exists():
            return {}, ""

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        match = FRONTMATTER_PATTERN.match(content)
        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1)) or {}
                text = match.group(2).strip()
                return frontmatter, text
            except yaml.YAMLError as e:
                logger.error(f"YAML parse error in {filepath}: {e}")
                return {}, content
        return {}, content.strip()

    def _write_md_file(self, filepath: Path, frontmatter: dict, content: str):
        """Writes frontmatter and content back cleanly in Obsidian format."""
        # 'sort_keys=False' preserves the order of the keys
        fm_yaml = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False)
        new_content = f"---\n{fm_yaml}---\n{content}\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    def get_document_data(self, filepath: Path) -> tuple[str, str]:
        """Returns (summary, plain_text) of the document."""
        fm, text = self._read_md_file(filepath)
        return fm.get("ai_summary", PENDING_SUMMARY_TEXT), text

    def get_subfolder_summaries(self, folder_path: Path) -> str:
        """Collects the ai_summary from the .index.md of every direct subfolder of folder_path."""
        lines = []
        for entry in sorted(folder_path.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir():
                continue
            index_fm, _ = self._read_md_file(entry / ".index.md")
            if not index_fm:
                continue
            summary = index_fm.get("ai_summary", PENDING_SUMMARY_TEXT)
            lines.append(f"- **{entry.name}/** — {summary}")
        return "\n".join(lines)

    def has_content_changed(self, filepath: Path) -> bool:
        """Compares the current document content with the last processed state. In
        particular it recognizes our own writing-back of the summary (the frontmatter
        changes but the content itself does not) and reports False for that."""
        fm, text = self._read_md_file(filepath)
        return get_content_hash(text) != fm.get("content_hash")

    def get_filemap_summary(self, relative_path: str) -> str:
        """Reads the summary from the central .ai_map.json."""
        if not self.ai_map_path.exists():
            return PENDING_SUMMARY_TEXT

        with open(self.ai_map_path, "r", encoding="utf-8") as f:
            ai_map = json.load(f)

        return ai_map.get("files", {}).get(relative_path, PENDING_SUMMARY_TEXT)

    def update_vault_data(self, filepath: Path, result: dict):
        """Updates the document frontmatter and the central .ai_map.json (file entry)
        based on the summarizer agent's result. The folder level (.index.md and the
        .ai_map.json directory entry) is maintained separately via update_folder_data()."""

        # 1. Update the document frontmatter
        fm, text = self._read_md_file(filepath)
        fm["ai_summary"] = result.get("document_summary")
        fm["content_hash"] = get_content_hash(text)
        fm["linked_files"] = extract_linked_files(self.vault_root, text)
        fm["last_modified"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._write_md_file(filepath, fm, text)

        # 2. Update the central .ai_map.json (file entry)
        if self.ai_map_path.exists():
            with open(self.ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)
        else:
            ai_map = {"directories": {}, "files": {}}

        rel_path = filepath.relative_to(self.vault_root).as_posix()

        if "files" not in ai_map:
            ai_map["files"] = {}
        ai_map["files"][rel_path] = result.get("filemap_summary")

        with open(self.ai_map_path, "w", encoding="utf-8") as f:
            json.dump(ai_map, f, indent=2, ensure_ascii=False)

    def build_folder_summary_input(self, folder_path: Path) -> dict:
        """Builds the input data for the FolderSummarizer agent: the current file map,
        the subfolder summaries and this folder's existing summaries."""
        if self.ai_map_path.exists():
            with open(self.ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)
        else:
            ai_map = {"directories": {}, "files": {}}

        rel_dir = folder_path.relative_to(self.vault_root).as_posix()
        index_fm, _ = self._read_md_file(folder_path / ".index.md")

        return {
            "files_overview": build_file_map_content(self.vault_root, folder_path, ai_map),
            "subfolder_summaries": self.get_subfolder_summaries(folder_path),
            "prev_folder_summary": index_fm.get("ai_summary", PENDING_SUMMARY_TEXT),
            "prev_dirmap_summary": ai_map.get("directories", {}).get(rel_dir, PENDING_SUMMARY_TEXT),
        }

    def update_folder_data(self, folder_path: Path, result: dict):
        """Updates .index.md (frontmatter + file map) and the directory entry
        in .ai_map.json, based on the FolderSummarizer agent's result."""
        if self.ai_map_path.exists():
            with open(self.ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)
        else:
            ai_map = {"directories": {}, "files": {}}

        rel_dir = folder_path.relative_to(self.vault_root).as_posix()
        if "directories" not in ai_map:
            ai_map["directories"] = {}
        if rel_dir and rel_dir != ".":
            ai_map["directories"][rel_dir] = result.get("dirmap_summary")

        with open(self.ai_map_path, "w", encoding="utf-8") as f:
            json.dump(ai_map, f, indent=2, ensure_ascii=False)

        index_path = folder_path / ".index.md"
        index_fm, _ = self._read_md_file(index_path)

        index_fm["ai_summary"] = result.get("folder_summary")
        index_fm["folder_name"] = folder_path.name
        index_fm["is_directory_index"] = True
        index_fm["last_modified"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        file_map_content = build_file_map_content(self.vault_root, folder_path, ai_map)
        self._write_md_file(index_path, index_fm, file_map_content)

    def refresh_file_map(self, folder_path: Path):
        """Rebuilds the file map in the body of an .index.md from the current state of
        .ai_map.json, without touching the summary (frontmatter). Used by the periodic
        maintenance pass so that deleted files disappear from the map immediately.
        Writes the file ONLY if the map actually changed (otherwise every maintenance
        run would needlessly rewrite every .index.md in the vault and trigger a
        watchdog event)."""
        index_path = folder_path / ".index.md"
        if not index_path.exists():
            return

        ai_map = {"directories": {}, "files": {}}
        if self.ai_map_path.exists():
            with open(self.ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)

        index_fm, current_content = self._read_md_file(index_path)
        file_map_content = build_file_map_content(self.vault_root, folder_path, ai_map)
        if file_map_content == current_content:
            return
        self._write_md_file(index_path, index_fm, file_map_content)


def process_obsidian_file(vault_root: Path, filepath: Path) -> bool:
    """
    The main function called by the watchdog.

    Returns whether this changed the summary of the direct parent folder (the basis for
    a possible cascade further up, see FolderSummaryScheduler in scheduler.py).
    """
    manager = ObsidianVaultManager(vault_root)

    # The path for the map must use POSIX notation (forward slashes)
    rel_path_str = filepath.relative_to(vault_root).as_posix()

    # 1. Daten zusammenziehen
    prev_doc_summary, current_content = manager.get_document_data(filepath)
    prev_filemap_summary = manager.get_filemap_summary(rel_path_str)

    # 2. Build the input (previous_content is left empty, or carries the old summary)
    input_data = {
        "current_content": current_content,
        "previous_content": "", # No longer available at the filesystem level
        "prev_doc_summary": prev_doc_summary,
        "prev_filemap_summary": prev_filemap_summary,
    }

    logger.info(f"[{filepath.name}] Building summaries from the Obsidian data...")

    # 3. Run the agent
    from src.agentic import SummarizerAgent, run_agent_session
    session = run_agent_session(agent=SummarizerAgent, raw_input=input_data)

    # 4. Speichern
    if session.is_successful:
        manager.update_vault_data(filepath, session.final_result.model_dump())
        logger.info(f"[{filepath.name}] YAML and .ai_map.json (file entry) updated.")
        # The file summary changed -> have the folder summary regenerated.
        return process_folder_summary(vault_root, filepath.parent)

    logger.error(f"[{filepath.name}] Agent error. The vault was not modified.")
    return False


def process_folder_summary(vault_root: Path, folder_path: Path) -> bool:
    """
    Called after the summary of a file or subfolder inside folder_path has changed.
    Invokes the FolderSummarizer agent to update the .index.md (the detailed summary)
    and this folder's short entry in the .ai_map.json.

    Returns whether folder_summary or dirmap_summary actually changed as a result (the
    basis for a cascade to the parent folder).
    """
    manager = ObsidianVaultManager(vault_root)
    rel_dir = folder_path.relative_to(vault_root).as_posix()
    dir_label = rel_dir if rel_dir != "." else "(vault-root)"

    input_data = manager.build_folder_summary_input(folder_path)

    logger.info(f"[{dir_label}] Building folder summary...")

    from src.agentic import FolderSummarizerAgent, run_agent_session
    session = run_agent_session(agent=FolderSummarizerAgent, raw_input=input_data)

    if not session.is_successful:
        logger.error(f"[{dir_label}] FolderSummarizer agent error. Folder summary not modified.")
        return False

    result = session.final_result.model_dump()
    changed = (
        result.get("folder_summary") != input_data.get("prev_folder_summary")
        or result.get("dirmap_summary") != input_data.get("prev_dirmap_summary")
    )
    manager.update_folder_data(folder_path, result)
    logger.info(f"[{dir_label}] .index.md and .ai_map.json (folder entry) updated.")
    return changed


def register_pending_file(filepath: Path, vault_root: Path) -> bool:
    """Registers a just-created note in .ai_map.json IMMEDIATELY - with a placeholder
    summary (PENDING_SUMMARY_TEXT) - and rebuilds the file map in the parent folder's
    .index.md, so the new file shows up there right away instead of only at the next
    maintenance run.

    This function does NOT produce the real summary: it calls no agent. The placeholder
    is the signal map_maintenance uses to schedule the summary.

    Returns True if an entry was written.
    """
    root = Path(vault_root).resolve()
    target = Path(filepath).resolve()

    # System files (.index.md, .ai_map.json, _-prefixed ...) do not belong in the map.
    if not is_summarizable_path(target):
        return False

    try:
        rel_path = target.relative_to(root).as_posix()
    except ValueError:
        logger.warning(f"[Map] File lies outside the vault, no AI map entry: {target}")
        return False

    ai_map_path = root / ".ai_map.json"
    ai_map = _load_ai_map(ai_map_path)

    ai_map["files"][rel_path] = PENDING_SUMMARY_TEXT
    _register_parent_dirs(ai_map, target, root)

    with open(ai_map_path, "w", encoding="utf-8") as f:
        json.dump(ai_map, f, indent=2, ensure_ascii=False)
    logger.info(f"[Map] New file registered in the AI map: {rel_path}")

    # Rebuild the file map in the folder's .index.md; only writes on a real change.
    ObsidianVaultManager(root).refresh_file_map(target.parent)
    return True


def _load_ai_map(ai_map_path: Path) -> dict:
    """Reads .ai_map.json tolerantly: if it is missing or corrupted, a fresh, empty
    structure is returned."""
    ai_map = {}
    if ai_map_path.exists():
        try:
            with open(ai_map_path, "r", encoding="utf-8") as f:
                ai_map = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[Map] .ai_map.json not readable, rebuilding it: {e}")
            ai_map = {}
    if not isinstance(ai_map, dict):
        ai_map = {}
    ai_map.setdefault("directories", {})
    ai_map.setdefault("files", {})
    return ai_map


def _register_parent_dirs(ai_map: dict, target: Path, root: Path) -> None:
    """Registers all parent folders up to the vault root, without overwriting folder
    summaries that already exist."""
    for parent in target.parents:
        if parent == root:
            break
        ai_map["directories"].setdefault(parent.relative_to(root).as_posix(), PENDING_SUMMARY_TEXT)


def move_map_entry(old_path: Path, new_path: Path, vault_root: Path) -> bool:
    """Moves the .ai_map.json entry of a moved/renamed note along with it: the old key
    disappears and the new one inherits the EXISTING summary (no regeneration - the
    content did not change during the move). If the old entry was missing, the new one
    is registered as pending.

    Afterwards the file maps of the .index.md in BOTH the source and destination folder
    are rebuilt, so the note does not appear twice or not at all.

    Returns True if an entry was written.
    """
    root = Path(vault_root).resolve()
    source = Path(old_path)
    target = Path(new_path).resolve()

    if not is_summarizable_path(target):
        return False

    try:
        rel_new = target.relative_to(root).as_posix()
        # The source no longer exists; resolve() without strict is correct here.
        rel_old = source.resolve().relative_to(root).as_posix()
    except ValueError:
        logger.warning(f"[Map] Move outside the vault, no AI map entry: {source} -> {target}")
        return False

    ai_map_path = root / ".ai_map.json"
    ai_map = _load_ai_map(ai_map_path)

    carried = ai_map["files"].pop(rel_old, None) or PENDING_SUMMARY_TEXT
    ai_map["files"][rel_new] = carried
    _register_parent_dirs(ai_map, target, root)

    with open(ai_map_path, "w", encoding="utf-8") as f:
        json.dump(ai_map, f, indent=2, ensure_ascii=False)
    logger.info(f"[Map] AI map entry moved: {rel_old} -> {rel_new}")

    manager = ObsidianVaultManager(root)
    for folder in {source.parent, target.parent}:
        if folder.is_dir():
            manager.refresh_file_map(folder)
    return True


def register_pending_directory(dirpath: Path, vault_root: Path) -> bool:
    """Registers a newly created folder in .ai_map.json IMMEDIATELY, so it shows up in
    format_ai_map() - otherwise an agent could create a folder it then cannot see
    itself. Folder summaries that already exist are left untouched; the real summary is
    produced later by the folder-summary pipeline.

    Returns True if a new entry was created.
    """
    root = Path(vault_root).resolve()
    target = Path(dirpath).resolve()

    if target == root or not target.is_dir():
        return False
    # Hidden / technical folders (.git, .obsidian ...) do not belong in the map.
    if any(part.startswith(".") or part.startswith("_") for part in target.parts[len(root.parts):]):
        return False

    try:
        rel_dir = target.relative_to(root).as_posix()
    except ValueError:
        logger.warning(f"[Map] Folder lies outside the vault, no AI map entry: {target}")
        return False

    ai_map_path = root / ".ai_map.json"
    ai_map = _load_ai_map(ai_map_path)

    if rel_dir in ai_map["directories"]:
        return False

    ai_map["directories"][rel_dir] = PENDING_SUMMARY_TEXT
    _register_parent_dirs(ai_map, target, root)

    with open(ai_map_path, "w", encoding="utf-8") as f:
        json.dump(ai_map, f, indent=2, ensure_ascii=False)
    logger.info(f"[Map] New folder registered in the AI map: {rel_dir}")
    return True


def remove_map_entry(path: Path, vault_root: Path) -> bool:
    """Removes the .ai_map.json entry of a deleted note or folder - including ALL
    entries beneath it, since deleting a folder removes all of its content.

    The path no longer exists by the time this is called, so a file can no longer be
    distinguished from a folder: every key that matches exactly or lies below the path
    is simply removed. For a file that is exactly one key.

    Returns True if at least one entry was removed.
    """
    root = Path(vault_root).resolve()
    target = Path(path)

    try:
        rel = target.resolve().relative_to(root).as_posix()
    except ValueError:
        return False
    if not rel or rel == ".":
        return False

    ai_map_path = root / ".ai_map.json"
    if not ai_map_path.exists():
        return False
    ai_map = _load_ai_map(ai_map_path)

    prefix = f"{rel}/"
    removed: list[str] = []
    for section in ("files", "directories"):
        for key in [k for k in ai_map[section] if k == rel or k.startswith(prefix)]:
            del ai_map[section][key]
            removed.append(key)

    if not removed:
        return False

    with open(ai_map_path, "w", encoding="utf-8") as f:
        json.dump(ai_map, f, indent=2, ensure_ascii=False)
    logger.info(f"[Map] Removed {len(removed)} AI map entry/entries for: {rel}")

    # Rebuild the file map in the parent folder, so the entry disappears there too.
    parent = target.parent
    if parent.is_dir():
        ObsidianVaultManager(root).refresh_file_map(parent)
    return True
