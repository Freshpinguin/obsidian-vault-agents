# src/navigation/vault_mutation.py
"""Writing counterparts to vault_navigation.py: create folders and files, edit and
move files. Uses the same tolerant path resolution (see vault_navigation._resolve)
for targets that already exist (edit_file, move_file source). For NEW paths
(create_directory, create_file, move_file destination) there is no fuzzy lookup
(nothing to match against) - those are only normalized and guarded against escaping
the vault (see _resolve_new_path).

When a call here actually writes a file, the already-running watchdog picks it up
automatically (see main.py): it detects the change and triggers the normal
summarization pipeline (summarizer agent, .ai_map.json, .index.md cascade).

Exception: create_file additionally registers the new file in .ai_map.json straight
away (register_pending_file), because the summarizer runs on a 30-minute delay and
the note would otherwise be invisible to the agents until then.
"""
import unicodedata
from pathlib import Path

import yaml

from src.core.obsidian_processor import (
    is_summarizable_path,
    move_map_entry,
    register_pending_directory,
    register_pending_file,
    remove_map_entry,
)
from src.core.logging_config import logger
from src.navigation.vault_navigation import (
    ROOT_ALIASES,
    VaultPathError,
    _read_md,
    _resolve,
    _strip_frontmatter,
    _vault_path,
    _vault_root,
)


def _resolve_new_path(path: str | Path, vault_root: Path | None = None) -> Path:
    """Resolves a NEW (not yet existing) vault path: normalizes spelling (Unicode,
    slash direction, leading slashes, leading root identifiers such as "data/")
    WITHOUT fuzzy lookup - for new paths there is nothing to match against. Rejects
    paths that would lead outside the vault."""
    root = _vault_root(vault_root).resolve()
    raw = unicodedata.normalize("NFC", str(path)).replace("\\", "/").strip()
    segments = [s for s in raw.strip("/").split("/") if s not in ("", ".")]

    while len(segments) > 1 and segments[0].casefold() in ROOT_ALIASES:
        segments = segments[1:]

    if not segments:
        raise VaultPathError("No path was provided.")

    resolved = root.joinpath(*segments).resolve()
    if resolved != root and root not in resolved.parents:
        raise VaultPathError(f"Path lies outside the vault: {path}")
    return resolved


def create_directory(path: str, vault_root: Path | None = None) -> str:
    """Creates a new (empty) folder in the vault, including any missing parent folders."""
    root = _vault_root(vault_root)
    try:
        target = _resolve_new_path(path, root)
    except VaultPathError as e:
        return f"Error: {e}"

    if target.exists():
        kind = "folder" if target.is_dir() else "file"
        return f"Error: '{_vault_path(target, root)}' already exists ({kind})."

    target.mkdir(parents=True)
    register_pending_directory(target, root)
    logger.info(f"[Mutation] Folder created: {_vault_path(target, root)}")
    return f"Folder '{_vault_path(target, root)}' was created."


def create_file(path: str, content: str, vault_root: Path | None = None) -> str:
    """Creates a new Markdown file with the given content (without frontmatter - the
    summarization pipeline adds that automatically). Missing parent folders are
    created along the way."""
    root = _vault_root(vault_root)
    try:
        target = _resolve_new_path(path, root)
    except VaultPathError as e:
        return f"Error: {e}"

    if target.suffix != ".md":
        return f"Error: only .md files are supported ('{path}')."
    if not is_summarizable_path(target):
        return f"Error: '{_vault_path(target, root)}' is not a valid file name for a note."
    if target.exists():
        return f"Error: '{_vault_path(target, root)}' already exists."

    target.parent.mkdir(parents=True, exist_ok=True)
    # Defensive: if the supplied content accidentally contains YAML frontmatter (e.g.
    # because an agent copied another file's content as a template), strip it instead
    # of letting it end up in the new file.
    target.write_text(_strip_frontmatter(content) + "\n", encoding="utf-8")
    register_pending_file(target, root)
    logger.info(f"[Mutation] File created: {_vault_path(target, root)}")
    return f"File '{_vault_path(target, root)}' was created."


def edit_file(path: str, content: str, vault_root: Path | None = None) -> str:
    """Replaces the content of an existing file (below the YAML frontmatter, which is
    preserved unchanged - the summarization pipeline updates it on the next run
    anyway). The path does not have to match exactly (see _resolve)."""
    root = _vault_root(vault_root)
    try:
        target = _resolve(path, root, expect="file")
    except VaultPathError as e:
        return f"Error: {e}"

    if not is_summarizable_path(target):
        return f"Error: '{_vault_path(target, root)}' is a system file and cannot be edited."

    fm, _ = _read_md(target)
    # Defensive: content may itself contain (possibly stale) frontmatter, e.g. if the
    # caller used the complete old file content as a template - that would otherwise be
    # written BEFORE the freshly read, current frontmatter and end up duplicated.
    body = _strip_frontmatter(content)
    if fm:
        fm_yaml = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        new_text = f"---\n{fm_yaml}---\n{body}\n"
    else:
        new_text = body + "\n"

    target.write_text(new_text, encoding="utf-8")
    logger.info(f"[Mutation] File edited: {_vault_path(target, root)}")
    return f"File '{_vault_path(target, root)}' was updated."


def move_file(path: str, new_path: str, vault_root: Path | None = None) -> str:
    """Moves/renames an existing file. The source is resolved tolerantly (see
    _resolve); the destination must be a new, not yet existing .md path."""
    root = _vault_root(vault_root)
    try:
        source = _resolve(path, root, expect="file")
    except VaultPathError as e:
        return f"Error: {e}"

    if not is_summarizable_path(source):
        return f"Error: '{_vault_path(source, root)}' is a system file and cannot be moved."

    try:
        destination = _resolve_new_path(new_path, root)
    except VaultPathError as e:
        return f"Error: {e}"

    if destination.suffix != ".md":
        return f"Error: destination must end in .md ('{new_path}')."
    if destination.exists():
        return f"Error: '{_vault_path(destination, root)}' already exists."

    source_label = _vault_path(source, root)
    dest_label = _vault_path(destination, root)

    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    move_map_entry(source, destination, root)
    logger.info(f"[Mutation] File moved: {source_label} -> {dest_label}")
    return f"File moved: '{source_label}' -> '{dest_label}'."


def delete_file(path: str, vault_root: Path | None = None) -> str:
    """Deletes an existing .md file from the vault."""
    root = _vault_root(vault_root)
    try:
        target = _resolve(path, root, expect="file")
    except VaultPathError as e:
        return f"Error: {e}"

    if not is_summarizable_path(target):
        return f"Error: '{_vault_path(target, root)}' is a system file and cannot be deleted."

    label = _vault_path(target, root)
    try:
        target.unlink()
        remove_map_entry(target, root)
        logger.info(f"[Mutation] File deleted: {label}")
        return f"File '{label}' was deleted."
    except Exception as e:
        return f"Error deleting '{label}': {e}"
