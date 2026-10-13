# src/routes/health/__init__.py
from fastapi import APIRouter

router = APIRouter(tags=["health"])

# Import route files to register endpoints directly on router
from src.routes.health.get_health import get_health, health_check

__all__ = [
    "router",
    "get_health",
    "health_check",
]
