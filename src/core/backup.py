import os
import subprocess
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.core.logging_config import logger

WATCH_DIR = os.getenv("WATCH_DIR") or os.getenv("VAULT_PATH") or ("/app/data" if os.path.exists("/app/data") else "./data.example")

def run_auto_backup(interval_minutes=int(os.getenv("BACKUP_INTERVAL_MINUTES", 60 * 12))):
    """Pushes changes to the remote repository at regular intervals."""
    logger.info(f"[Backup] Git auto-sync started. Interval: {interval_minutes} minutes.")

    while True:
        time.sleep(interval_minutes * 60)
        try:
            # 1. Stage all changed files
            subprocess.run(["git", "add", "."], cwd=WATCH_DIR, check=True)
            
            # 2. Check whether there are any changes at all (restricted to WATCH_DIR,
            # otherwise "git status" also reports changes outside data/, e.g. in src/,
            # which "git add ." here would never have staged -> "nothing to commit")
            status = subprocess.run(
                ["git", "status", "--porcelain", "."],
                cwd=WATCH_DIR,
                capture_output=True,
                text=True
            )
            
            if not status.stdout.strip():
                # No changes -> do nothing
                continue
            
            # 3. Committen
            commit_msg = f"Auto-Backup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=WATCH_DIR, check=True)
            
            # 4. Nach GitHub pushen
            subprocess.run(["git", "push", "origin", "main"], cwd=WATCH_DIR, check=True)
            logger.info(f"[Backup] Erfolgreich gepusht um {datetime.now().strftime('%H:%M:%S')}.")

        except subprocess.CalledProcessError as e:
            logger.error(f"[Backup] Error during git sync: {e}")