# src/routes/files/get_file_content.py
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Query

from src.navigation.vault_navigation import (
    VaultPathError,
    _read_md,
    _resolve,
    _vault_path,
    _vault_root,
)
from src.routes.files import router
from src.schemas.file_schema import FileContentResponse


def _load_file_response(path_str: str) -> FileContentResponse:
    """Lädt und parst eine Datei aus dem Vault."""
    root = _vault_root().resolve()


    try:
        resolved = _resolve(path_str, root, expect="file")
    except VaultPathError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"Pfad '{path_str}' ist keine Datei.")

    raw_content = resolved.read_text(encoding="utf-8")
    fm, body = _read_md(resolved)

    stat = resolved.stat()
    last_mod = fm.get("last_modified") or datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    linked = fm.get("linked_files") or []
    if isinstance(linked, str):
        linked = [linked]

    rel_path = _vault_path(resolved, root)

    return FileContentResponse(
        path=rel_path,
        name=resolved.name,
        raw_content=raw_content,
        body=body,
        frontmatter=fm,
        ai_summary=fm.get("ai_summary"),
        tags=tags,
        linked_files=linked,
        last_modified=str(last_mod),
    )


@router.get("/content", response_model=FileContentResponse)
def get_file_content(path: str = Query(..., description="Relativer oder vollständiger Vault-Pfad zur Datei")):
    """Gibt den Inhalt und Metadaten einer Datei anhand des Pfads zurück."""
    return _load_file_response(path)


@router.get("/{path:path}", response_model=FileContentResponse)
def get_file_content_by_path(path: str):
    """Alias für get_file_content über Pfad-Parameter (z.B. /files/Kulturen/Beispielvolk.md)."""
    return _load_file_response(path)
