# src/core/__init__.py
from src.core.logging_config import SessionLogger, logger
from src.core.backup import run_auto_backup
from src.core.core_engine import ensure_directory_index, update_ai_map
from src.core.obsidian_processor import (
    FRONTMATTER_PATTERN,
    ObsidianVaultManager,
    is_summarizable_path,
    process_folder_summary,
    process_obsidian_file,
)
from src.core.rebuild import rebuild_universe
from src.core.scheduler import FolderSummaryScheduler, SummaryScheduler
from src.core.events import vault_events, VaultEventBroadcaster

__all__ = [
    "logger",
    "SessionLogger",
    "run_auto_backup",
    "ensure_directory_index",
    "update_ai_map",
    "FRONTMATTER_PATTERN",
    "ObsidianVaultManager",
    "is_summarizable_path",
    "process_folder_summary",
    "process_obsidian_file",
    "rebuild_universe",
    "FolderSummaryScheduler",
    "SummaryScheduler",
]
