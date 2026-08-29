import os
import time
import threading
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Importiere unsere Logik aus der anderen Datei
from src.obsidian_processor import is_summarizable_path
from src.scheduler import SummaryScheduler
from src.backup import run_auto_backup
from src.map_maintenance import run_ai_map_maintenance
from src.logging_config import logger
from src.chat_routes import router as chat_router

# Die FastAPI App initialisieren
app = FastAPI(title="Obsidian Vault Agents")
app.include_router(chat_router)

# Der Ordner, den wir überwachen (im Docker-Container ist das /app/data)
WATCH_DIR = os.getenv("WATCH_DIR", "/app/data")
VAULT_ROOT = Path(WATCH_DIR)

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
        if event.is_directory or self._is_ignored(event.src_path):
            return
        logger.info(f"[Watchdog] Erstellt: {event.src_path}")
        self._maybe_schedule(event.src_path)

    def on_modified(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        logger.info(f"[Watchdog] Geändert: {event.src_path}")
        self._maybe_schedule(event.src_path)

    def on_deleted(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        logger.info(f"[Watchdog] Gelöscht: {event.src_path}")
        summary_scheduler.cancel(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        logger.info(f"[Watchdog] Verschoben: {event.src_path} -> {event.dest_path}")
        summary_scheduler.cancel(Path(event.src_path))
        self._maybe_schedule(event.dest_path)

def run_watchdog():
    """Startet den Beobachter-Prozess."""
    event_handler = MarkdownHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=True)
    observer.start()
    logger.info(f"[Watchdog] Gestartet. Überwache: {WATCH_DIR}")

    try:
        while True:
            time.sleep(1)
    except Exception as e:
        observer.stop()
        logger.error(f"[Watchdog] Beendet: {e}")
    observer.join()

# Dieser Block wird ausgeführt, sobald Docker den Server startet
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

# Chat-Frontend: einzelne, self-contained HTML-Datei im Repo-Root (ein Verzeichnis über src/)
FRONTEND_PATH = Path(__file__).resolve().parent.parent / "index.html"


@app.get("/")
def read_root():
    return FileResponse(FRONTEND_PATH)


@app.get("/health")
def health_check():
    return {"status": "Obsidian Vault Agents läuft."}