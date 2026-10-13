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
    """Requests an immediate new AI summary for an open note."""
    root = VAULT_ROOT.resolve()

    try:
        resolved = _resolve(body.path, root, expect="file")
    except VaultPathError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"'{body.path}' is not a file.")

    if not is_summarizable_path(resolved):
        raise HTTPException(
            status_code=400,
            detail=f"File '{resolved.name}' cannot be summarized (regular .md notes only).",
        )

    logger.info(f"[Summary-Route] Manual summary requested for: {_vault_path(resolved, root)}")

    try:
        # Runs the summarizer agent immediately and updates the YAML frontmatter & .ai_map.json
        process_obsidian_file(root, resolved)
        updated_file = _load_file_response(str(resolved))

        return RequestSummaryResponse(
            path=updated_file.path,
            success=True,
            ai_summary=updated_file.ai_summary,
            file=updated_file,
            message="AI summary updated successfully.",
        )
    except Exception as e:
        logger.error(f"[Summary-Route] Error summarizing {resolved.name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error during AI summarization: {str(e)}",
        )


# Alias
request_file_summary = post_summary
