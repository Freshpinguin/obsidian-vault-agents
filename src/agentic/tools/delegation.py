# src/agentic/tools/delegation.py
"""WikiTool-Instanzen, die andere Agenten oder spezialisierte Subsysteme aufrufen."""
from src.schemas.tool_args import (
    AskLibrarianArgs,
    ReasoningArgs,
    WebSearchArgs,
)
from src.schemas.tool_schema import WikiTool
from src.agentic.agents.reasoner import run_reasoning
from src.agentic.agents.web_search import web_search
from src.navigation import load_files


def _ask_librarian_tool(question: str) -> str:
    # Bewusst verzögerter Import, um Zyklen mit agents.librarian zu vermeiden
    from src.agentic.agents.librarian import ask_librarian

    result = ask_librarian(question)
    if not result.is_successful:
        return "Fehler: Der Librarian konnte zu dieser Frage keine Antwort recherchieren."
    output = result.final_result

    if not output.sources:
        return f"{output.answer}\n\nQuellen: (keine)"

    # Die vom Librarian zitierten Quellen-Dateien direkt im Volltext mitliefern, damit
    # der aufrufende Agent sie nicht noch per load_files nachladen muss.
    return (
        f"{output.answer}\n\nQuellen: {', '.join(output.sources)}"
        f"\n\n## Volltext der zitierten Quellen\n\n{load_files(output.sources)}"
    )


ask_librarian_tool = WikiTool(
    name="ask_librarian",
    description="Stellt dem Librarian-Agenten eine Recherche-Frage zum Vault-Inhalt und liefert dessen mit Quellen belegte Antwort zurück.",
    parameters=AskLibrarianArgs,
    func=_ask_librarian_tool,
)

web_search_tool = WikiTool(
    name="web_search",
    description="Recherchiert per echter Websuche im realen Internet (nicht der Vault) – für Realismus-/Faktenchecks von Universum-Konzepten und für allgemeine Fragen, die aktuelles Weltwissen brauchen.",
    parameters=WebSearchArgs,
    func=web_search,
)

reasoning_tool = WikiTool(
    name="deep_reasoning",
    description="Für komplexe Überlegungen oder das Ausformulieren längerer Texte mit viel Kontext. Optional: Vault-Pfade, deren Inhalt automatisch als Kontext mitgeschickt wird.",
    parameters=ReasoningArgs,
    func=run_reasoning,
)

__all__ = [
    "ask_librarian_tool",
    "web_search_tool",
    "reasoning_tool",
]
