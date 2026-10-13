# src/routes/frontend/get_frontend.py
from pathlib import Path

from fastapi.responses import FileResponse

from src.routes.frontend import router

# Chat frontend: a single self-contained HTML file in the repository root (four levels above this file)
FRONTEND_PATH = Path(__file__).resolve().parents[3] / "index.html"


@router.get("/")
def get_frontend():
    return FileResponse(FRONTEND_PATH, headers={"Cache-Control": "no-cache"})


# Alias
read_root = get_frontend
