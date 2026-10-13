# src/routes/files/get_files.py
from datetime import datetime
from pathlib import Path

from fastapi import Query

from src.navigation.vault_navigation import (
    VAULT_ROOT,
    _read_md,
    _vault_path,
    load_ai_map,
)
from src.routes.files import router
from src.schemas.file_schema import FileNode, FileTreeResponse


def _build_tree(
    directory: Path,
    root: Path,
    files_map: dict[str, str],
    dirs_map: dict[str, str],
    include_hidden: bool = False,
) -> tuple[list[FileNode], int, int]:
    """Baut rekursiv die Baumstruktur für ein Verzeichnis auf.
    Gibt (items, file_count, dir_count) zurück."""
    dir_nodes: list[FileNode] = []
    file_nodes: list[FileNode] = []
    total_files = 0
    total_dirs = 0

    try:
        entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except (PermissionError, FileNotFoundError):
        return [], 0, 0

    for entry in entries:
        name = entry.name
        # Ignoriere Git und standardmäßig versteckte Dateien/Ordner
        if name == ".git":
            continue
        if not include_hidden and name.startswith("."):
            continue

        rel_path = _vault_path(entry, root)

        if entry.is_dir():
            children, sub_files, sub_dirs = _build_tree(
                entry, root, files_map, dirs_map, include_hidden=include_hidden
            )
            total_files += sub_files
            total_dirs += 1 + sub_dirs

            # Summary aus .index.md oder ai_map
            index_path = entry / ".index.md"
            fm, _ = _read_md(index_path) if index_path.exists() else ({}, "")
            summary = fm.get("ai_summary") or dirs_map.get(rel_path)

            dir_nodes.append(
                FileNode(
                    name=name,
                    path=rel_path,
                    type="directory",
                    ai_summary=summary,
                    children=children,
                )
            )
        elif entry.is_file():
            # Nur Markdown oder generell alle Dateien? Markdown primär, andere auch falls vorhanden
            stat = entry.stat()
            last_mod = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

            fm, _ = _read_md(entry) if entry.suffix.lower() == ".md" else ({}, "")
            summary = fm.get("ai_summary") or files_map.get(rel_path)
            tags = fm.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            linked = fm.get("linked_files") or []
            if isinstance(linked, str):
                linked = [linked]

            total_files += 1
            file_nodes.append(
                FileNode(
                    name=name,
                    path=rel_path,
                    type="file",
                    size=stat.st_size,
                    last_modified=last_mod,
                    ai_summary=summary,
                    tags=tags,
                    linked_files=linked,
                )
            )

    return dir_nodes + file_nodes, total_files, total_dirs


@router.get("", response_model=FileTreeResponse)
def get_files(include_hidden: bool = Query(False, description="Versteckte Dateien/Ordner (.index.md etc.) anzeigen")):
    """Gibt die vollständige hierarchische Ordner- und Dateistruktur des Vaults zurück."""
    root = VAULT_ROOT.resolve()
    ai_map = load_ai_map(root)
    files_map = ai_map.get("files", {})
    dirs_map = ai_map.get("directories", {})

    items, total_files, total_dirs = _build_tree(
        root, root, files_map, dirs_map, include_hidden=include_hidden
    )

    return FileTreeResponse(
        root_path=str(root),
        total_files=total_files,
        total_directories=total_dirs,
        items=items,
    )
