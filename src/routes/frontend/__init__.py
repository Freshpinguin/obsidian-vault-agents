# src/routes/frontend/__init__.py
from fastapi import APIRouter

router = APIRouter(tags=["frontend"])

# Import route files to register endpoints directly on router
from src.routes.frontend.get_frontend import get_frontend, read_root

__all__ = [
    "router",
    "get_frontend",
    "read_root",
]
