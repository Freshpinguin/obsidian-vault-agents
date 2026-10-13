# src/routes/files/delete_file.py
from fastapi import HTTPException, Query

from src.core.logging_config import logger
from src.core.obsidian_processor import is_summarizable_path, remove_map_entry
from src.navigation.vault_navigation import (
    VaultPathError,
    _resolve,
    _vault_path,
    _vault_root,
)
from src.schemas.file_schema import DeleteFileResponse
from src.routes.files import router


@router.delete("/content", response_model=DeleteFileResponse)
def delete_file_content(path: str = Query(..., description="Relative or full vault path to the file")):
    """Deletes a note file from the vault."""
    root = _vault_root().resolve()


    try:
        resolved = _resolve(path, root, expect="file")
    except VaultPathError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"'{path}' is not a file.")

    if not is_summarizable_path(resolved):
        raise HTTPException(
            status_code=400,
            detail=f"System file '{resolved.name}' must not be deleted.",
        )

    rel_path = _vault_path(resolved, root)
    try:
        resolved.unlink()
        # Remove the entry from the AI map immediately, so agents do not see a phantom note.
        remove_map_entry(resolved, root)
        logger.info(f"[Mutation] File deleted from the frontend: {rel_path}")
        return DeleteFileResponse(
            path=rel_path,
            success=True,
            message=f"File '{resolved.name}' was deleted successfully.",
        )
    except Exception as e:
        logger.error(f"[Mutation] Error deleting {resolved}: {e}")
        raise HTTPException(status_code=500, detail=f"Error while deleting: {str(e)}")
