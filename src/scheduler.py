# src/scheduler.py
import threading
from pathlib import Path

from src.obsidian_processor import ObsidianVaultManager, process_obsidian_file, process_folder_summary
from src.logging_config import logger

DEBOUNCE_SECONDS = 30 * 60   # 30 Minuten

# Kaskadierende Ordner-Zusammenfassungen (Großeltern-Ordner und weiter nach oben)
# laufen bewusst langsamer als die direkte Datei-/Elternordner-Aktualisierung, damit
# bei vielen Änderungen in verschachtelten Unterordnern nicht bei jeder einzelnen
# sofort die gesamte Kette bis zur Wurzel neu berechnet wird.
CASCADE_DEBOUNCE_SECONDS = DEBOUNCE_SECONDS * 2


class FolderSummaryScheduler:
    """Kaskadiert Ordner-Zusammenfassungen nach oben (Großeltern-Ordner und weiter),
    nachdem sich die Zusammenfassung eines direkten Elternordners bereits geändert hat.

    Läuft mit CASCADE_DEBOUNCE_SECONDS statt DEBOUNCE_SECONDS und wird pro Ordner
    debounced: weitere Trigger für denselben Ordner innerhalb des Zeitfensters setzen
    den Timer zurück, damit bei vielen Änderungen in Unterordnern nicht wiederholt
    unnötig die gesamte Kette bis zur Wurzel neu berechnet wird. Nach Ablauf wird nur
    dann eine Ebene weiter nach oben kaskadiert, wenn sich die Zusammenfassung dieses
    Ordners durch den Lauf tatsächlich geändert hat.
    """

    def __init__(self, vault_root: Path, delay_seconds: int = CASCADE_DEBOUNCE_SECONDS):
        self.vault_root = vault_root
        self.delay_seconds = delay_seconds
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}

    def schedule(self, folder_path: Path):
        """Plant (oder verschiebt) die kaskadierende Ordner-Zusammenfassung für folder_path."""
        key = str(folder_path)
        with self._lock:
            existing = self._timers.get(key)
            if existing is not None:
                existing.cancel()
                logger.info(f"[FolderScheduler] Kaskaden-Timer für {folder_path} durch neue Änderung zurückgesetzt.")

            timer = threading.Timer(self.delay_seconds, self._run, args=(folder_path,))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

        logger.info(f"[FolderScheduler] Kaskadierende Ordner-Zusammenfassung für {folder_path} in {self.delay_seconds // 60} Minuten geplant.")

    def cancel(self, folder_path: Path):
        """Verwirft eine geplante Kaskaden-Zusammenfassung."""
        key = str(folder_path)
        with self._lock:
            existing = self._timers.pop(key, None)
        if existing is not None:
            existing.cancel()
            logger.info(f"[FolderScheduler] Geplante Kaskaden-Zusammenfassung für {folder_path} verworfen.")

    def _run(self, folder_path: Path):
        with self._lock:
            self._timers.pop(str(folder_path), None)
        try:
            changed = process_folder_summary(self.vault_root, folder_path)
            if changed and folder_path != self.vault_root:
                self.schedule(folder_path.parent)
        except Exception as e:
            logger.error(f"[FolderScheduler] Fehler beim Verarbeiten von {folder_path}: {e}")


class SummaryScheduler:
    """Verzögert die Zusammenfassung eines Dokuments um DEBOUNCE_SECONDS.

    Jede weitere inhaltliche Änderung am selben Dokument innerhalb des Zeitfensters
    setzt den Timer zurück und verwirft die zuvor geplante Ausführung. Events, die
    nur vom eigenen Zurückschreiben der Zusammenfassung stammen (der Dokumenteninhalt
    bleibt dabei unverändert), werden ignoriert, um eine Endlosschleife zu vermeiden.
    """

    def __init__(self, vault_root: Path, delay_seconds: int = DEBOUNCE_SECONDS):
        self.vault_root = vault_root
        self.delay_seconds = delay_seconds
        self._manager = ObsidianVaultManager(vault_root)
        self._lock = threading.Lock()
        self._timers: dict[str, threading.Timer] = {}
        self._folder_scheduler = FolderSummaryScheduler(vault_root)

    def schedule(self, filepath: Path, force: bool = False):
        """Plant (oder verschiebt) die Zusammenfassung für filepath.

        force=True überspringt die Inhaltswechsel-Prüfung, z.B. wenn bereits
        anderweitig feststeht, dass eine Zusammenfassung fehlt (siehe map_maintenance.py).
        """
        if not force and not self._manager.has_content_changed(filepath):
            logger.debug(f"[Scheduler] {filepath.name}: kein inhaltlicher Wechsel, ignoriere Event.")
            return

        key = str(filepath)
        with self._lock:
            existing = self._timers.get(key)
            if existing is not None:
                existing.cancel()
                logger.info(f"[Scheduler] Timer für {filepath.name} durch neue Änderung zurückgesetzt.")

            timer = threading.Timer(self.delay_seconds, self._run, args=(filepath,))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

        logger.info(f"[Scheduler] Zusammenfassung für {filepath.name} in {self.delay_seconds // 60} Minuten geplant.")

    def cancel(self, filepath: Path):
        """Verwirft eine geplante Zusammenfassung, z.B. weil die Datei gelöscht/verschoben wurde."""
        key = str(filepath)
        with self._lock:
            existing = self._timers.pop(key, None)
        if existing is not None:
            existing.cancel()
            logger.info(f"[Scheduler] Geplante Zusammenfassung für {filepath.name} verworfen.")

    def _run(self, filepath: Path):
        with self._lock:
            self._timers.pop(str(filepath), None)
        try:
            parent_folder_changed = process_obsidian_file(self.vault_root, filepath)
            grandparent = filepath.parent.parent
            if parent_folder_changed and filepath.parent != self.vault_root:
                self._folder_scheduler.schedule(grandparent)
        except Exception as e:
            logger.error(f"[Scheduler] Fehler beim Verarbeiten von {filepath}: {e}")
