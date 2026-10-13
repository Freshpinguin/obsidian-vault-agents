# src/agentic/tools/__init__.py
"""Werkzeug-Sammlung (WikiTools) für Agenten."""
from src.agentic.tools.vault_read import (
    directory_summaries_tool,
    file_summaries_tool,
    files_tool,
)
from src.agentic.tools.vault_write import (
    create_directory_tool,
    create_file_tool,
    edit_file_tool,
    move_file_tool,
    delete_file_tool,
)
from src.agentic.tools.delegation import (
    ask_librarian_tool,
    reasoning_tool,
    web_search_tool,
)
from src.agentic.tools.tasks import (
    check_task_status_tool,
    start_background_task_tool,
    update_plan_tool,
)

# Die "Standard-Fähigkeiten", die sowohl Chat- als auch Task-Agent bekommen
CONTENT_TOOLS = [
    files_tool,
    ask_librarian_tool,
    web_search_tool,
    reasoning_tool,
    create_directory_tool,
    create_file_tool,
    edit_file_tool,
    move_file_tool,
    delete_file_tool,
]

__all__ = [
    "CONTENT_TOOLS",
    "directory_summaries_tool",
    "file_summaries_tool",
    "files_tool",
    "create_directory_tool",
    "create_file_tool",
    "edit_file_tool",
    "move_file_tool",
    "delete_file_tool",
    "ask_librarian_tool",
    "reasoning_tool",
    "web_search_tool",
    "check_task_status_tool",
    "start_background_task_tool",
    "update_plan_tool",
]
