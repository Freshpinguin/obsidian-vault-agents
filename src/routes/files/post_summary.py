# src/routes/files/post_summary.py
from fastapi import HTTPException

from src.core.logging_config import logger
from src.core.obsidian_processor import is_summarizable_path, process_obsidian_file
from src.navigation.vault_navigation import (
    VAULT_ROOT,
    VaultPathError,
    _resolve,
    _vault_path,
)
from src.routes.files import router
from src.routes.files.get_file_content import _load_file_response
from src.schemas.file_schema import RequestSummaryRequest, RequestSummaryResponse


@router.post("/summary", response_model=RequestSummaryResponse)
def post_summary(body: RequestSummaryRequest):
    """Fordert eine sofortige neue KI-Zusammenfassung für eine geöffnete Notiz an."""
    root = VAULT_ROOT.resolve()

    try:
        resolved = _resolve(body.path, root, expect="file")
    except VaultPathError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"'{body.path}' ist keine Datei.")

    if not is_summarizable_path(resolved):
        raise HTTPException(
            status_code=400,
            detail=f"Datei '{resolved.name}' kann nicht zusammengefasst werden (nur reguläre .md Notizen).",
        )

    logger.info(f"[Summary-Route] Manuelle Zusammenfassung angefordert für: {_vault_path(resolved, root)}")

    try:
        # Führt den Summarizer-Agenten sofort aus und aktualisiert YAML-Frontmatter & .ai_map.json
        process_obsidian_file(root, resolved)
        updated_file = _load_file_response(str(resolved))

        return RequestSummaryResponse(
            path=updated_file.path,
            success=True,
            ai_summary=updated_file.ai_summary,
            file=updated_file,
            message="KI-Zusammenfassung erfolgreich aktualisiert.",
        )
    except Exception as e:
        logger.error(f"[Summary-Route] Fehler bei der Zusammenfassung von {resolved.name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei der KI-Zusammenfassung: {str(e)}",
        )


# Alias
request_file_summary = post_summary
