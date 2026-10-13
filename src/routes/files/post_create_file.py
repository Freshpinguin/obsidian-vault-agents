# src/routes/files/post_create_file.py
from fastapi import HTTPException

from src.core.logging_config import logger
from src.core.obsidian_processor import is_summarizable_path, register_pending_file
from src.navigation.vault_mutation import _resolve_new_path
from src.navigation.vault_navigation import (
    VaultPathError,
    _vault_path,
    _vault_root,
)
from src.schemas.file_schema import CreateNoteRequest, MutationResponse
from src.routes.files import router


@router.post("/create-file", response_model=MutationResponse)
def post_create_file(body: CreateNoteRequest):
    """Creates a new note file (.md) in the vault."""
    root = _vault_root().resolve()

    raw_path = (body.path or "").strip()
    if raw_path and not raw_path.lower().endswith(".md"):
        raw_path += ".md"

    try:
        target = _resolve_new_path(raw_path, root)
    except VaultPathError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if target.suffix != ".md":
        raise HTTPException(
            status_code=400,
            detail="The note file must end in '.md'.",
        )

    if not is_summarizable_path(target):
        raise HTTPException(
            status_code=400,
            detail=f"The file name '{target.name}' is not permitted for notes.",
        )

    if target.exists():
        raise HTTPException(
            status_code=409,
            detail=f"File '{target.name}' already exists.",
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        content_to_write = body.content if body.content.endswith("\n") or not body.content else f"{body.content}\n"
        target.write_text(content_to_write, encoding="utf-8")
        # Do not wait for the watchdog: the new note should be in the AI map immediately.
        register_pending_file(target, root)
        rel_path = _vault_path(target, root)
        logger.info(f"[Mutation] New note created: {rel_path}")
        return MutationResponse(
            path=rel_path,
            success=True,
            message=f"Note '{target.name}' was created successfully.",
        )
    except Exception as e:
        logger.error(f"[Mutation] Error creating note {target}: {e}")
        raise HTTPException(status_code=500, detail=f"Error while creating the file: {str(e)}")
