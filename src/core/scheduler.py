# src/scheduler.py
import threading
from pathlib import Path

from src.core.obsidian_processor import ObsidianVaultManager, process_obsidian_file, process_folder_summary
from src.core.logging_config import logger

DEBOUNCE_SECONDS = 30 * 60   # 30 Minuten

# Cascading folder summaries (grandparent folders and further up) deliberately run
# more slowly than the direct file/parent-folder update, so that many changes in
# nested subfolders do not each immediately recompute the entire chain up to the root.
CASCADE_DEBOUNCE_SECONDS = DEBOUNCE_SECONDS * 2


class FolderSummaryScheduler:
    """Cascades folder summaries upwards (grandparent folders and beyond) after the
    summary of a direct parent folder has already changed.

    Runs with CASCADE_DEBOUNCE_SECONDS instead of DEBOUNCE_SECONDS and is debounced per
    folder: further triggers for the same folder within the time window reset the timer,
    so that many changes in subfolders do not repeatedly recompute the entire chain up
    to the root unnecessarily. Once it fires, it cascades one level further up only if
    this folder's summary actually changed during the run.
    """

    def __init__(self, vault_root: Path, delay_seconds: int = CASCADE_DEBOUNCE_SECONDS):
        self.vault_root = vault_root
        self.delay_seconds = delay_seconds
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}

    def schedule(self, folder_path: Path):
        """Schedules (or postpones) the cascading folder summary for folder_path."""
        key = str(folder_path)
        with self._lock:
            existing = self._timers.get(key)
            if existing is not None:
                existing.cancel()
                logger.info(f"[FolderScheduler] Cascade timer for {folder_path} reset by a new change.")

            timer = threading.Timer(self.delay_seconds, self._run, args=(folder_path,))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

        logger.info(f"[FolderScheduler] Cascading folder summary for {folder_path} scheduled in {self.delay_seconds // 60} minutes.")

    def cancel(self, folder_path: Path):
        """Discards a scheduled cascade summary."""
        key = str(folder_path)
        with self._lock:
            existing = self._timers.pop(key, None)
        if existing is not None:
            existing.cancel()
            logger.info(f"[FolderScheduler] Scheduled cascade summary for {folder_path} discarded.")

    def _run(self, folder_path: Path):
        with self._lock:
            self._timers.pop(str(folder_path), None)
        try:
            changed = process_folder_summary(self.vault_root, folder_path)
            if changed and folder_path != self.vault_root:
                self.schedule(folder_path.parent)
        except Exception as e:
            logger.error(f"[FolderScheduler] Error processing {folder_path}: {e}")


class SummaryScheduler:
    """Delays the summarization of a document by DEBOUNCE_SECONDS.

    Every further change to the content of the same document within the time window
    resets the timer and discards the previously scheduled run. Events that stem only
    from writing the summary back ourselves (the document content stays unchanged) are
    ignored, to avoid an endless loop.
    """

    def __init__(self, vault_root: Path, delay_seconds: int = DEBOUNCE_SECONDS):
        self.vault_root = vault_root
        self.delay_seconds = delay_seconds
        self._manager = ObsidianVaultManager(vault_root)
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}
        self._folder_scheduler = FolderSummaryScheduler(vault_root)

    def schedule(self, filepath: Path, force: bool = False):
        """Schedules (or postpones) the summarization of filepath.

        force=True skips the content-change check, e.g. when it is already
        otherwise established that a summary is missing (see map_maintenance.py).
        """
        if not force and not self._manager.has_content_changed(filepath):
            logger.debug(f"[Scheduler] {filepath.name}: no content change, ignoring event.")
            return

        key = str(filepath)
        with self._lock:
            existing = self._timers.get(key)
            if existing is not None:
                existing.cancel()
                logger.info(f"[Scheduler] Timer for {filepath.name} reset by a new change.")

            timer = threading.Timer(self.delay_seconds, self._run, args=(filepath,))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

        logger.info(f"[Scheduler] Summary for {filepath.name} scheduled in {self.delay_seconds // 60} minutes.")

    def cancel(self, filepath: Path):
        """Discards a scheduled summary, e.g. because the file was deleted or moved."""
        key = str(filepath)
        with self._lock:
            existing = self._timers.pop(key, None)
        if existing is not None:
            existing.cancel()
            logger.info(f"[Scheduler] Scheduled summary for {filepath.name} discarded.")

    def _run(self, filepath: Path):
        with self._lock:
            self._timers.pop(str(filepath), None)
        try:
            parent_folder_changed = process_obsidian_file(self.vault_root, filepath)
            grandparent = filepath.parent.parent
            if parent_folder_changed and filepath.parent != self.vault_root:
                self._folder_scheduler.schedule(grandparent)
        except Exception as e:
            logger.error(f"[Scheduler] Error processing {filepath}: {e}")
