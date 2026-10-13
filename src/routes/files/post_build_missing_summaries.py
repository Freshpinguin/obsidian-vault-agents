# src/routes/files/post_build_missing_summaries.py
from fastapi import HTTPException
from pathlib import Path

from src.core.logging_config import logger
from src.core.core_engine import ensure_directory_index
from src.core.obsidian_processor import (
    PENDING_SUMMARY_TEXT,
    ObsidianVaultManager,
    is_summarizable_path,
    process_obsidian_file,
    process_folder_summary,
)
from src.navigation.vault_navigation import VAULT_ROOT
from src.routes.files import router
from src.schemas.file_schema import BuildMissingSummariesResponse


@router.post("/build-missing-summaries", response_model=BuildMissingSummariesResponse)
def post_build_missing_summaries():
    """Scans the entire vault and automatically generates AI summaries for all notes
    and folders that do not have a summary yet."""
    root = VAULT_ROOT.resolve()
    manager = ObsidianVaultManager(root)

    logger.info(f"[Build-Summaries] Starting scan for missing summaries in {root}...")

    # 1. Identify missing file summaries
    missing_files: list[Path] = []
    for md_file in sorted(root.rglob("*.md")):
        if not is_summarizable_path(md_file):
            continue
        try:
            fm, text = manager._read_md_file(md_file)
            summary = (fm.get("ai_summary") or "").strip()
            if not summary or summary == PENDING_SUMMARY_TEXT:
                missing_files.append(md_file)
        except Exception as e:
            logger.warning(f"[Build-Summaries] Could not check {md_file.name}: {e}")

    logger.info(f"[Build-Summaries] Found {len(missing_files)} files without a summary.")

    processed_files = 0
    errors: list[str] = []

    # 2. Generate the file summaries one after another
    for md_file in missing_files:
        try:
            success = process_obsidian_file(root, md_file)
            if success:
                processed_files += 1
        except Exception as e:
            err_msg = f"{md_file.name}: {str(e)}"
            logger.error(f"[Build-Summaries] Error summarizing {err_msg}")
            errors.append(err_msg)

    # 3. Check folders and generate missing folder summaries (.index.md)
    processed_folders = 0
    for folder in sorted(root.rglob("*")):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name.startswith("_"):
            continue
        try:
            ensure_directory_index(str(folder))
            index_path = folder / ".index.md"
            index_fm, _ = manager._read_md_file(index_path)
            f_summary = (index_fm.get("ai_summary") or "").strip()
            if not f_summary or f_summary == PENDING_SUMMARY_TEXT:
                process_folder_summary(root, folder)
                processed_folders += 1
        except Exception as e:
            logger.warning(f"[Build-Summaries] Folder {folder.name} could not be summarized: {e}")

    msg = (
        f"Created {processed_files} of {len(missing_files)} missing file summaries and {processed_folders} folder summaries."
        if (len(missing_files) > 0 or processed_folders > 0)
        else "All notes and folders already have a summary."
    )

    return BuildMissingSummariesResponse(
        success=True,
        files_processed=processed_files,
        total_missing_files=len(missing_files),
        folders_processed=processed_folders,
        errors=errors,
        message=msg,
    )


# Alias
build_missing_summaries = post_build_missing_summaries
