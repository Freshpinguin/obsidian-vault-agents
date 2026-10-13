# src/routes/files/post_build_missing_summaries.py
from fastapi import HTTPException
from pathlib import Path

from src.core.logging_config import logger
from src.core.core_engine import ensure_directory_index
from src.core.obsidian_processor import (
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
    """Durchsucht den gesamten Vault und generiert automatisch KI-Zusammenfassungen
    für alle Notizen und Ordner, die noch keine Zusammenfassung besitzen."""
    root = VAULT_ROOT.resolve()
    manager = ObsidianVaultManager(root)

    logger.info(f"[Build-Summaries] Starte Scan nach fehlenden Zusammenfassungen in {root}...")

    # 1. Fehlende Datei-Zusammenfassungen identifizieren
    missing_files: list[Path] = []
    for md_file in sorted(root.rglob("*.md")):
        if not is_summarizable_path(md_file):
            continue
        try:
            fm, text = manager._read_md_file(md_file)
            summary = (fm.get("ai_summary") or "").strip()
            if not summary or summary.startswith("Zusammenfassung ausstehend"):
                missing_files.append(md_file)
        except Exception as e:
            logger.warning(f"[Build-Summaries] Konnte {md_file.name} nicht prüfen: {e}")

    logger.info(f"[Build-Summaries] {len(missing_files)} Dateien ohne Zusammenfassung gefunden.")

    processed_files = 0
    errors: list[str] = []

    # 2. Datei-Zusammenfassungen nacheinander generieren
    for md_file in missing_files:
        try:
            success = process_obsidian_file(root, md_file)
            if success:
                processed_files += 1
        except Exception as e:
            err_msg = f"{md_file.name}: {str(e)}"
            logger.error(f"[Build-Summaries] Fehler bei Zusammenfassung von {err_msg}")
            errors.append(err_msg)

    # 3. Ordner prüfen und fehlende Ordner-Zusammenfassungen (.index.md) generieren
    processed_folders = 0
    for folder in sorted(root.rglob("*")):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name.startswith("_"):
            continue
        try:
            ensure_directory_index(str(folder))
            index_path = folder / ".index.md"
            index_fm, _ = manager._read_md_file(index_path)
            f_summary = (index_fm.get("ai_summary") or "").strip()
            if not f_summary or f_summary.startswith("Ordner-Zusammenfassung ausstehend") or f_summary.startswith("Zusammenfassung ausstehend"):
                process_folder_summary(root, folder)
                processed_folders += 1
        except Exception as e:
            logger.warning(f"[Build-Summaries] Ordner {folder.name} konnte nicht zusammengefasst werden: {e}")

    msg = (
        f"{processed_files} von {len(missing_files)} fehlenden Datei-Zusammenfassungen und {processed_folders} Ordner-Zusammenfassungen erstellt."
        if (len(missing_files) > 0 or processed_folders > 0)
        else "Alle Notizen und Ordner verfügen bereits über eine Zusammenfassung."
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
