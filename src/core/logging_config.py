import logging
from logging.handlers import RotatingFileHandler
import os

# Base directory for logs
LOG_DIR = os.getenv("LOG_DIR", "logs")
LLM_DIR = os.path.join(LOG_DIR, "llm_details")

# Create the directories if they do not exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(LLM_DIR, exist_ok=True)

# How many session log files to keep at most
MAX_SESSION_LOGS = 100

# ==========================================
# 1. Main Logger Setup (Rolling)
# ==========================================
logger = logging.getLogger("scifi_engine")
logger.setLevel(logging.INFO)

# Prevent log records from being emitted twice
if not logger.handlers:
    # Konsolen-Ausgabe (optional, aber hilfreich beim Entwickeln)
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File output (rolling: max 5MB per file, max 5 backups)
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "engine.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
