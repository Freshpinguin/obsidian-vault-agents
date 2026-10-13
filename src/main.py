import os
import time
import threading
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (.env) before any further module initialization
load_dotenv()

from fastapi import FastAPI
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import our logic from the modules
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

# Initialize the FastAPI app
app = FastAPI(title="Obsidian Vault Agents")
app.include_router(api_router)

from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parents[1]   # Repository root
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# The folder we watch (/app/data in the Docker container, ./data.example locally)
WATCH_DIR = os.getenv("WATCH_DIR") or os.getenv("VAULT_PATH") or ("/app/data" if os.path.exists("/app/data") else "./data.example")
VAULT_ROOT = Path(WATCH_DIR).resolve()

from src.core.events import vault_events

# Debounced: summaries are only generated 30 minutes after the last change
summary_scheduler = SummaryScheduler(vault_root=VAULT_ROOT)

class MarkdownHandler(FileSystemEventHandler):
    """Defines what happens when a file changes (whether through manual editing, the
    engine itself, or a sync tool such as Syncthing)."""

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
                logger.error(f"[Watchdog] AI map folder entry failed for {event.src_path}: {e}")
            vault_events.broadcast("dir_created", {"path": event.src_path})
            return
        logger.info(f"[Watchdog] Created: {event.src_path}")
        # Register in .ai_map.json + .index.md straight away, so a note created by hand
        # (or via sync) is immediately visible to the agents. Without this it would only
        # appear once the 30-minute-delayed summarizer runs.
        try:
            register_pending_file(Path(event.src_path), VAULT_ROOT)
        except Exception as e:
            logger.error(f"[Watchdog] AI map entry failed for {event.src_path}: {e}")
        self._maybe_schedule(event.src_path)
        vault_events.broadcast("created", {"path": event.src_path})

    def on_modified(self, event):
        if self._is_ignored(event.src_path):
            return
        if event.is_directory:
            return
        logger.info(f"[Watchdog] Modified: {event.src_path}")
        self._maybe_schedule(event.src_path)
        vault_events.broadcast("modified", {"path": event.src_path})

    def on_deleted(self, event):
        if self._is_ignored(event.src_path):
            return
        if event.is_directory:
            # Removing the folder removes all of its content from the AI map.
            try:
                remove_map_entry(Path(event.src_path), VAULT_ROOT)
            except Exception as e:
                logger.error(f"[Watchdog] AI map cleanup failed for {event.src_path}: {e}")
            vault_events.broadcast("dir_deleted", {"path": event.src_path})
            return
        logger.info(f"[Watchdog] Deleted: {event.src_path}")
        # Remove manually deleted notes from the AI map immediately too.
        try:
            remove_map_entry(Path(event.src_path), VAULT_ROOT)
        except Exception as e:
            logger.error(f"[Watchdog] AI map cleanup failed for {event.src_path}: {e}")
        summary_scheduler.cancel(Path(event.src_path))
        vault_events.broadcast("deleted", {"path": event.src_path})

    def on_moved(self, event):
        if self._is_ignored(event.src_path):
            return
        if event.is_directory:
            vault_events.broadcast("dir_moved", {"src_path": event.src_path, "dest_path": event.dest_path})
            return
        logger.info(f"[Watchdog] Verschoben: {event.src_path} -> {event.dest_path}")
        # Re-register notes moved by hand (e.g. inside Obsidian) immediately too.
        try:
            move_map_entry(Path(event.src_path), Path(event.dest_path), VAULT_ROOT)
        except Exception as e:
            logger.error(f"[Watchdog] AI map move failed for {event.src_path}: {e}")
        summary_scheduler.cancel(Path(event.src_path))
        self._maybe_schedule(event.dest_path)
        vault_events.broadcast("moved", {"src_path": event.src_path, "dest_path": event.dest_path})

_observer = None

def run_watchdog():
    """Starts the watchdog observer process."""
    global _observer
    event_handler = MarkdownHandler()
    _observer = Observer()
    _observer.schedule(event_handler, str(VAULT_ROOT), recursive=True)
    _observer.start()
    logger.info(f"[Watchdog] Started. Watching: {VAULT_ROOT}")

    try:
        while _observer.is_alive():
            time.sleep(1)
    except Exception as e:
        logger.error(f"[Watchdog] Beendet: {e}")
    finally:
        if _observer.is_alive():
            _observer.stop()
            _observer.join(timeout=2)

# This block runs as soon as the server starts
@app.on_event("startup")
def startup_event():
    # Start the watchdog in the background (daemon thread)
    watchdog_thread = threading.Thread(target=run_watchdog, daemon=True)
    watchdog_thread.start()

    # Start the git auto-backup in the background (daemon thread)
    backup_thread = threading.Thread(target=run_auto_backup, daemon=True)
    backup_thread.start()

    # Start the AI map maintenance in the background (daemon thread):
    # removes orphaned entries and schedules pending summaries
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
