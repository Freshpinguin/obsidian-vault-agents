import os
import subprocess
import time
from datetime import datetime

from src.logging_config import logger

WATCH_DIR = os.getenv("WATCH_DIR", "/app/data")

def run_auto_backup(interval_minutes=int(os.getenv("BACKUP_INTERVAL_MINUTES", 60 * 12))):
    """Pusht Änderungen in regelmäßigen Abständen nach GitHub."""
    logger.info(f"[Backup] Git Auto-Sync gestartet. Intervall: {interval_minutes} Minuten.")

    while True:
        time.sleep(interval_minutes * 60)
        try:
            # 1. Alle geänderten Dateien stagen
            subprocess.run(["git", "add", "."], cwd=WATCH_DIR, check=True)
            
            # 2. Prüfen, ob es überhaupt Änderungen gibt (auf WATCH_DIR beschränkt,
            # sonst meldet "git status" auch Änderungen außerhalb von data/, z.B. in src/,
            # die "git add ." hier nie gestaged hätte -> "nothing to commit")
            status = subprocess.run(
                ["git", "status", "--porcelain", "."],
                cwd=WATCH_DIR,
                capture_output=True,
                text=True
            )
            
            if not status.stdout.strip():
                # Keine Änderungen -> wir machen nichts
                continue
            
            # 3. Committen
            commit_msg = f"Auto-Backup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=WATCH_DIR, check=True)
            
            # 4. Nach GitHub pushen
            subprocess.run(["git", "push", "origin", "main"], cwd=WATCH_DIR, check=True)
            logger.info(f"[Backup] Erfolgreich gepusht um {datetime.now().strftime('%H:%M:%S')}.")

        except subprocess.CalledProcessError as e:
            logger.error(f"[Backup] Fehler beim Git Sync: {e}")