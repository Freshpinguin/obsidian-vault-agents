# src/routes/session/__init__.py
from fastapi import APIRouter

router = APIRouter(prefix="/sessions", tags=["chat"])

# Import route files to register endpoints directly on router
from src.routes.session.delete_session import delete_session
from src.routes.session.post_message import post_message, send_message
from src.routes.session.post_session import post_session, start_session

__all__ = [
    "router",
    "delete_session",
    "post_message",
    "post_session",
    "send_message",
    "start_session",
]
