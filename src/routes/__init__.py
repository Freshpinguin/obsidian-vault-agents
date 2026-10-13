# src/routes/__init__.py
from fastapi import APIRouter

from src.routes.frontend import router as frontend_router
from src.routes.health import router as health_router
from src.routes.session import router as session_router
from src.routes.files import router as files_router

router = APIRouter()
router.include_router(frontend_router)
router.include_router(health_router)
router.include_router(session_router)
router.include_router(files_router)

# Backward-compatibility alias
chat_router = session_router

__all__ = [
    "router",
    "frontend_router",
    "health_router",
    "session_router",
    "files_router",
    "chat_router",
]
