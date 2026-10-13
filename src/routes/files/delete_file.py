# src/routes/files/delete_file.py
from fastapi import HTTPException, Query

from src.core.logging_config import logger
from src.core.obsidian_processor import is_summarizable_path
from src.navigation.vault_navigation import (
    VaultPathError,
    _resolve,
    _vault_path,
    _vault_root,
)
from src.schemas.file_schema import DeleteFileResponse
from src.routes.files import router


@router.delete("/content", response_model=DeleteFileResponse)
def delete_file_content(path: str = Query(..., description="Relativer oder vollständiger Vault-Pfad zur Datei")):
    """Löscht eine Notizdatei aus dem Vault."""
    root = _vault_root().resolve()


    try:
        resolved = _resolve(path, root, expect="file")
    except VaultPathError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"'{path}' ist keine Datei.")

    if not is_summarizable_path(resolved):
        raise HTTPException(
            status_code=400,
            detail=f"Systemdatei '{resolved.name}' darf nicht gelöscht werden.",
        )

    rel_path = _vault_path(resolved, root)
    try:
        resolved.unlink()
        logger.info(f"[Mutation] Datei im Frontend gelöscht: {rel_path}")
        return DeleteFileResponse(
            path=rel_path,
            success=True,
            message=f"Datei '{resolved.name}' wurde erfolgreich gelöscht.",
        )
    except Exception as e:
        logger.error(f"[Mutation] Fehler beim Löschen von {resolved}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Löschen: {str(e)}")
