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
    """Prüft in regelmäßigen Abständen die .ai_map.json:
    1. Einträge, deren Datei/Ordner nicht mehr existiert, werden entfernt.
    2. Notizen, die auf der Platte liegen, aber (noch) nicht in der Map stehen, werden
       nachgetragen - etwa wenn sie angelegt wurden, während der Server nicht lief.
    3. Für Dateien mit noch ausstehender Zusammenfassung wird diese eingeplant.
    """
    ai_map_path = vault_root / ".ai_map.json"
    logger.info(f"[Maintenance] AI-Map-Wartung gestartet. Intervall: {interval_minutes} Minuten.")

    while True:
        try:
            _check_ai_map(vault_root, ai_map_path, summary_scheduler)
        except Exception as e:
            logger.error(f"[Maintenance] Fehler bei der AI-Map-Wartung: {e}")
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
            logger.info(f"[Maintenance] Entferne verwaisten Datei-Eintrag aus AI-Map: {rel_path}")
            del files[rel_path]
            changed = True

    for rel_dir in list(directories.keys()):
        if not (vault_root / rel_dir).is_dir():
            logger.info(f"[Maintenance] Entferne verwaisten Ordner-Eintrag aus AI-Map: {rel_dir}")
            del directories[rel_dir]
            changed = True

    # Nachtragen: Notizen, die existieren, aber in der Map fehlen. Der Watchdog erledigt
    # das im Betrieb sofort (siehe main.py on_created); dieser Durchlauf fängt die Fälle
    # auf, in denen der Server beim Anlegen nicht lief.
    for filepath in sorted(vault_root.rglob("*.md")):
        if not is_summarizable_path(filepath):
            continue
        rel_path = filepath.relative_to(vault_root).as_posix()
        if rel_path in files:
            continue
        logger.info(f"[Maintenance] Fehlende Notiz in AI-Map nachgetragen: {rel_path}")
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
        logger.info("[Maintenance] AI-Map bereinigt und gespeichert.")

    # Datei-Map in allen .index.md-Dateien auf den aktuellen Stand bringen,
    # damit z.B. inzwischen gelöschte Dateien dort verschwinden, auch ohne
    # dass in diesem Ordner gerade eine neue Zusammenfassung generiert wurde.
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
        # force=True: die Zusammenfassung fehlt nachweislich, unabhängig davon,
        # ob sich der Dateiinhalt seit dem letzten content_hash geändert hat.
        summary_scheduler.schedule(filepath, force=True)
        pending_count += 1

    if pending_count:
        logger.info(f"[Maintenance] {pending_count} ausstehende Zusammenfassung(en) eingeplant.")
