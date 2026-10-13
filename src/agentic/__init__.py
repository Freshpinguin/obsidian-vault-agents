# src/agentic/__init__.py
"""Fassade des agentic-Pakets: die fünf nach außen angebotenen Symbole."""
from src.agentic.agents.chat import continue_wiki_chat, start_wiki_chat
from src.agentic.agents.folder_summarizer import FolderSummarizerAgent
from src.agentic.agents.summarizer import SummarizerAgent
from src.agentic.engine import run_agent_session

__all__ = [
    "start_wiki_chat",
    "continue_wiki_chat",
    "run_agent_session",
    "SummarizerAgent",
    "FolderSummarizerAgent",
]
