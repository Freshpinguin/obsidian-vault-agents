# src/core/map_maintenance.py
import json
import time
from pathlib import Path

from src.core.obsidian_processor import (
    PENDING_SUMMARY_TEXT,
    ObsidianVaultManager,
    is_summarizable_path,
)
from src.core.scheduler import SummaryScheduler
from src.core.logging_config import logger


def run_ai_map_maintenance(vault_root: Path, summary_scheduler: SummaryScheduler, interval_minutes: int):
    """Checks the .ai_map.json at regular intervals:
    1. Entries whose file/folder no longer exists are removed.
    2. Notes that are on disk but not (yet) in the map are added - for instance when
       they were created while the server was not running.
    3. For files whose summary is still pending, that summary is scheduled.
    """
    ai_map_path = vault_root / ".ai_map.json"
    logger.info(f"[Maintenance] AI map maintenance started. Interval: {interval_minutes} minutes.")

    while True:
        try:
            _check_ai_map(vault_root, ai_map_path, summary_scheduler)
        except Exception as e:
            logger.error(f"[Maintenance] Error during AI map maintenance: {e}")
        time.sleep(interval_minutes * 60)


def _check_ai_map(vault_root: Path, ai_map_path: Path, summary_scheduler: SummaryScheduler):
    if not ai_map_path.exists():
        return

    with open(ai_map_path, "r", encoding="utf-8") as f:
        ai_map = json.load(f)

    files = ai_map.get("files", {})
    directories = ai_map.get("directories", {})
    changed = False

    for rel_path in list(files.keys()):
        if not (vault_root / rel_path).exists():
            logger.info(f"[Maintenance] Removing orphaned file entry from the AI map: {rel_path}")
            del files[rel_path]
            changed = True

    for rel_dir in list(directories.keys()):
        if not (vault_root / rel_dir).is_dir():
            logger.info(f"[Maintenance] Removing orphaned folder entry from the AI map: {rel_dir}")
            del directories[rel_dir]
            changed = True

    # Backfill: notes that exist but are missing from the map. The watchdog handles this
    # immediately at runtime (see main.py on_created); this pass catches the cases where
    # the server was not running when they were created.
    for filepath in sorted(vault_root.rglob("*.md")):
        if not is_summarizable_path(filepath):
            continue
        rel_path = filepath.relative_to(vault_root).as_posix()
        if rel_path in files:
            continue
        logger.info(f"[Maintenance] Backfilled missing note into the AI map: {rel_path}")
        files[rel_path] = PENDING_SUMMARY_TEXT
        rel_dir = filepath.parent.relative_to(vault_root).as_posix()
        if rel_dir not in (".", ""):
            directories.setdefault(rel_dir, PENDING_SUMMARY_TEXT)
        changed = True

    if changed:
        ai_map["files"] = files
        ai_map["directories"] = directories
        with open(ai_map_path, "w", encoding="utf-8") as f:
            json.dump(ai_map, f, indent=2, ensure_ascii=False)
        logger.info("[Maintenance] AI map cleaned up and saved.")

    # Bring the file map in every .index.md up to date, so that e.g. files deleted in
    # the meantime disappear there too, without a new summary having to be generated for
    # that folder.
    manager = ObsidianVaultManager(vault_root)
    for index_path in vault_root.rglob(".index.md"):
        manager.refresh_file_map(index_path.parent)

    pending_count = 0
    for rel_path, summary in files.items():
        if summary != PENDING_SUMMARY_TEXT:
            continue
        filepath = vault_root / rel_path
        if not is_summarizable_path(filepath):
            continue
        # force=True: the summary is demonstrably missing, regardless of whether the
        # file content has changed since the last content_hash.
        summary_scheduler.schedule(filepath, force=True)
        pending_count += 1

    if pending_count:
        logger.info(f"[Maintenance] Scheduled {pending_count} pending summary/summaries.")
