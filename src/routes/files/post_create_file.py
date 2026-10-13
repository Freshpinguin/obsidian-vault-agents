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
    """Erstellt eine neue Notizdatei (.md) im Vault."""
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
            detail="Die Notizdatei muss mit '.md' enden.",
        )

    if not is_summarizable_path(target):
        raise HTTPException(
            status_code=400,
            detail=f"Dateiname '{target.name}' ist für Notizen nicht zulässig.",
        )

    if target.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Datei '{target.name}' existiert bereits.",
        )

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        content_to_write = body.content if body.content.endswith("\n") or not body.content else f"{body.content}\n"
        target.write_text(content_to_write, encoding="utf-8")
        # Nicht auf den Watchdog warten: Die neue Notiz soll sofort in der AI-Map stehen.
        register_pending_file(target, root)
        rel_path = _vault_path(target, root)
        logger.info(f"[Mutation] Neue Notiz erstellt: {rel_path}")
        return MutationResponse(
            path=rel_path,
            success=True,
            message=f"Notiz '{target.name}' wurde erfolgreich erstellt.",
        )
    except Exception as e:
        logger.error(f"[Mutation] Fehler beim Erstellen der Notiz {target}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Erstellen der Datei: {str(e)}")
