# src/routes/files/post_move.py
from fastapi import HTTPException

from src.core.logging_config import logger
from src.core.obsidian_processor import is_summarizable_path, move_map_entry
from src.navigation.vault_mutation import _resolve_new_path
from src.navigation.vault_navigation import (
    VaultPathError,
    _resolve,
    _vault_path,
    _vault_root,
)
from src.schemas.file_schema import MoveNodeRequest, MutationResponse
from src.routes.files import router


@router.post("/move", response_model=MutationResponse)
def post_move(body: MoveNodeRequest):
    """Verschiebt eine Datei oder Notiz im Vault an einen neuen Pfad."""
    root = _vault_root().resolve()

    try:
        source = _resolve(body.path, root, expect="file")
    except VaultPathError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not is_summarizable_path(source):
        raise HTTPException(
            status_code=400,
            detail=f"Systemdatei '{source.name}' darf nicht verschoben werden.",
        )

    try:
        destination = _resolve_new_path(body.new_path, root)
    except VaultPathError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if destination.suffix != ".md":
        raise HTTPException(
            status_code=400,
            detail="Das Ziel muss eine Markdown-Datei (.md) sein.",
        )

    if destination.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Zieldatei '{destination.name}' existiert bereits.",
        )

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        # AI-Map-Eintrag mitziehen, damit die Notiz nicht unter dem alten Pfad
        # haengen bleibt und die bisherige Zusammenfassung erhalten bleibt.
        move_map_entry(source, destination, root)
        dest_vault_path = _vault_path(destination, root)
        src_vault_path = _vault_path(source, root)
        logger.info(f"[Mutation] Datei verschoben: {src_vault_path} -> {dest_vault_path}")
        return MutationResponse(
            path=dest_vault_path,
            success=True,
            message=f"Datei '{source.name}' wurde erfolgreich nach '{dest_vault_path}' verschoben.",
        )
    except Exception as e:
        logger.error(f"[Mutation] Fehler beim Verschieben von {source} nach {destination}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Verschieben: {str(e)}")
