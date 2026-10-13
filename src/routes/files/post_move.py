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
    """Moves a file or note within the vault to a new path."""
    root = _vault_root().resolve()

    try:
        source = _resolve(body.path, root, expect="file")
    except VaultPathError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not is_summarizable_path(source):
        raise HTTPException(
            status_code=400,
            detail=f"System file '{source.name}' must not be moved.",
        )

    try:
        destination = _resolve_new_path(body.new_path, root)
    except VaultPathError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if destination.suffix != ".md":
        raise HTTPException(
            status_code=400,
            detail="The destination must be a Markdown file (.md).",
        )

    if destination.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Destination file '{destination.name}' already exists.",
        )

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        # Carry the AI map entry along, so the note does not linger under the old path
        # and its existing summary is preserved.
        move_map_entry(source, destination, root)
        dest_vault_path = _vault_path(destination, root)
        src_vault_path = _vault_path(source, root)
        logger.info(f"[Mutation] File moved: {src_vault_path} -> {dest_vault_path}")
        return MutationResponse(
            path=dest_vault_path,
            success=True,
            message=f"File '{source.name}' was moved successfully to '{dest_vault_path}'.",
        )
    except Exception as e:
        logger.error(f"[Mutation] Error moving {source} to {destination}: {e}")
        raise HTTPException(status_code=500, detail=f"Error while moving: {str(e)}")
