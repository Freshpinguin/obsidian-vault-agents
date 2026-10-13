"""Agent definitions for the Obsidian vault system.

Five agents run through the engine (multi-turn, structured response, tools):
- ChatAgent
- TaskAgent
- LibrarianAgent
- SummarizerAgent
- FolderSummarizerAgent

Two are one-shot SDK calls without a session:
- reasoner
- web_search
"""
