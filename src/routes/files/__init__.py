# src/routes/files/__init__.py
from fastapi import APIRouter

router = APIRouter(prefix="/files", tags=["files"])

# Import the individual routes (they register themselves on the router)
# Important: import specific paths such as get_events BEFORE the catch-all /{path:path} in get_file_content.
from src.routes.files.get_events import get_events
from src.routes.files.get_files import get_files
from src.routes.files.post_summary import post_summary
from src.routes.files.post_build_missing_summaries import post_build_missing_summaries
from src.routes.files.put_file_content import put_file_content
from src.routes.files.delete_file import delete_file_content
from src.routes.files.post_move import post_move
from src.routes.files.post_create_file import post_create_file
from src.routes.files.get_file_content import get_file_content

__all__ = [
    "router",
    "get_events",
    "get_files",
    "post_summary",
    "post_build_missing_summaries",
    "put_file_content",
    "delete_file_content",
    "post_move",
    "post_create_file",
    "get_file_content",
]

