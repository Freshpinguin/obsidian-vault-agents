import os
import time
import threading
from pathlib import Path
from dotenv import load_dotenv

# Umgebungsvariablen (.env) vor weiteren Modul-Initialisierungen laden
load_dotenv()

from fastapi import FastAPI
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Importiere unsere Logik aus den Modulen
from src.core.obsidian_processor import (
    is_summarizable_path,
    move_map_entry,
    register_pending_directory,
    register_pending_file,
    remove_map_entry,
)
from src.core.scheduler import SummaryScheduler
from src.core.backup import run_auto_backup
from src.core.logging_config import logger
from src.core.map_maintenance import run_ai_map_maintenance
from src.routes import router as api_router

# Die FastAPI App initialisieren
app = FastAPI(title="Obsidian Vault Agents")
app.include_router(api_router)

from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parents[1]   # Repo-Wurzel
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Der Ordner, den wir überwachen (im Docker-Container /app/data, lokal ./data.example)
WATCH_DIR = os.getenv("WATCH_DIR") or os.getenv("VAULT_PATH") or ("/app/data" if os.path.exists("/app/data") else "./data.example")
VAULT_ROOT = Path(WATCH_DIR).resolve()

from src.core.events import vault_events

# Debounced: Zusammenfassungen werden erst 30min nach der letzten Änderung erzeugt
summary_scheduler = SummaryScheduler(vault_root=VAULT_ROOT)

class MarkdownHandler(FileSystemEventHandler):
    """Definiert, was passiert, wenn eine Datei geändert wird (egal ob durch
    manuelle Bearbeitung, die Engine selbst oder einen Sync wie Syncthing)."""

    def _is_ignored(self, path: str) -> bool:
        return ".git" in path.split(os.sep)

    def _maybe_schedule(self, path: str):
        filepath = Path(path)
        if is_summarizable_path(filepath):
            summary_scheduler.schedule(filepath)

    def on_created(self, event):
        if self._is_ignored(event.src_path):
            return
        if event.is_directory:
            try:
                register_pending_directory(Path(event.src_path), VAULT_ROOT)
            except Exception as e:
                logger.error(f"[Watchdog] AI-Map-Ordnereintrag fehlgeschlagen fuer {event.src_path}: {e}")
            vault_events.broadcast("dir_created", {"path": event.src_path})
            return
        logger.info(f"[Watchdog] Erstellt: {event.src_path}")
        # Sofort in .ai_map.json + .index.md vormerken, damit eine von Hand (oder per
        # Sync) angelegte Notiz fuer die Agenten unmittelbar sichtbar ist. Ohne das
        # taucht sie erst auf, wenn der um 30 Minuten verzoegerte Summarizer laeuft.
        try:
            register_pending_file(Path(event.src_path), VAULT_ROOT)
        except Exception as e:
            logger.error(f"[Watchdog] AI-Map-Eintrag fehlgeschlagen fuer {event.src_path}: {e}")
        self._maybe_schedule(event.src_path)
        vault_events.broadcast("created", {"path": event.src_path})

    def on_modified(self, event):
        if self._is_ignored(event.src_path):
            return
        if event.is_directory:
            return
        logger.info(f"[Watchdog] Geändert: {event.src_path}")
        self._maybe_schedule(event.src_path)
        vault_events.broadcast("modified", {"path": event.src_path})

    def on_deleted(self, event):
        if self._is_ignored(event.src_path):
            return
        if event.is_directory:
            # Mit dem Ordner verschwindet sein gesamter Inhalt aus der AI-Map.
            try:
                remove_map_entry(Path(event.src_path), VAULT_ROOT)
            except Exception as e:
                logger.error(f"[Watchdog] AI-Map-Aufraeumen fehlgeschlagen fuer {event.src_path}: {e}")
            vault_events.broadcast("dir_deleted", {"path": event.src_path})
            return
        logger.info(f"[Watchdog] Gelöscht: {event.src_path}")
        # Auch von Hand geloeschte Notizen sofort aus der AI-Map nehmen.
        try:
            remove_map_entry(Path(event.src_path), VAULT_ROOT)
        except Exception as e:
            logger.error(f"[Watchdog] AI-Map-Aufraeumen fehlgeschlagen fuer {event.src_path}: {e}")
        summary_scheduler.cancel(Path(event.src_path))
        vault_events.broadcast("deleted", {"path": event.src_path})

    def on_moved(self, event):
        if self._is_ignored(event.src_path):
            return
        if event.is_directory:
            vault_events.broadcast("dir_moved", {"src_path": event.src_path, "dest_path": event.dest_path})
            return
        logger.info(f"[Watchdog] Verschoben: {event.src_path} -> {event.dest_path}")
        # Auch von Hand (z.B. in Obsidian) verschobene Notizen sofort umtragen.
        try:
            move_map_entry(Path(event.src_path), Path(event.dest_path), VAULT_ROOT)
        except Exception as e:
            logger.error(f"[Watchdog] AI-Map-Umzug fehlgeschlagen fuer {event.src_path}: {e}")
        summary_scheduler.cancel(Path(event.src_path))
        self._maybe_schedule(event.dest_path)
        vault_events.broadcast("moved", {"src_path": event.src_path, "dest_path": event.dest_path})

_observer = None

def run_watchdog():
    """Startet den Beobachter-Prozess."""
    global _observer
    event_handler = MarkdownHandler()
    _observer = Observer()
    _observer.schedule(event_handler, str(VAULT_ROOT), recursive=True)
    _observer.start()
    logger.info(f"[Watchdog] Gestartet. Überwache: {VAULT_ROOT}")

    try:
        while _observer.is_alive():
            time.sleep(1)
    except Exception as e:
        logger.error(f"[Watchdog] Beendet: {e}")
    finally:
        if _observer.is_alive():
            _observer.stop()
            _observer.join(timeout=2)

# Dieser Block wird ausgeführt, sobald der Server startet
@app.on_event("startup")
def startup_event():
    # Starte den Watchdog im Hintergrund (Daemon-Thread)
    watchdog_thread = threading.Thread(target=run_watchdog, daemon=True)
    watchdog_thread.start()

    # Starte den Git Auto-Backup im Hintergrund (Daemon-Thread)
    backup_thread = threading.Thread(target=run_auto_backup, daemon=True)
    backup_thread.start()

    # Starte die AI-Map-Wartung im Hintergrund (Daemon-Thread):
    # entfernt verwaiste Einträge und plant ausstehende Zusammenfassungen ein
    maintenance_interval = int(os.getenv("MAP_MAINTENANCE_INTERVAL_MINUTES", 60))
    maintenance_thread = threading.Thread(
        target=run_ai_map_maintenance,
        args=(VAULT_ROOT, summary_scheduler, maintenance_interval),
        daemon=True,
    )
    maintenance_thread.start()

@app.on_event("shutdown")
def shutdown_event():
    global _observer
    if _observer and _observer.is_alive():
        _observer.stop()
        _observer.join(timeout=2)
