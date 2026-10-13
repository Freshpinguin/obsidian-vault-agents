# src/agentic/__init__.py
"""Facade of the agentic package: the five symbols offered to the outside.

This package encapsulates all LLM and agent functionality:
- `agents/`: declarations of the WikiAgent instances and specialized sub-agents
- `engine/`: ReAct execution loop, compaction, model rotation, background jobs and guards
- `tools/`: modular WikiTool definitions for vault reads/writes and delegation

Outside of `src/agentic/`, only the facade symbols defined here may be accessed
(enforced statically via an AST scan test).
"""
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
