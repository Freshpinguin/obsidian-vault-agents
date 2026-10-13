# src/agentic/tools/delegation.py
"""WikiTool instances that call other agents or specialized subsystems."""
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
    # Deliberately deferred import to avoid cycles with agents.librarian
    from src.agentic.agents.librarian import ask_librarian

    result = ask_librarian(question)
    if not result.is_successful:
        return "Error: the librarian could not research an answer to this question."
    output = result.final_result

    if not output.sources:
        return f"{output.answer}\n\nSources: (none)"

    # Include the full text of the source files cited by the librarian, so the calling
    # agent does not have to load them again via load_files.
    return (
        f"{output.answer}\n\nSources: {', '.join(output.sources)}"
        f"\n\n## Full text of the cited sources\n\n{load_files(output.sources)}"
    )


ask_librarian_tool = WikiTool(
    name="ask_librarian",
    description="Asks the librarian agent a research question about the vault contents and returns its source-backed answer.",
    parameters=AskLibrarianArgs,
    func=_ask_librarian_tool,
)

web_search_tool = WikiTool(
    name="web_search",
    description="Researches via a real web search on the live internet (not the vault) - for fact-checking concepts against reality and for general questions that need up-to-date world knowledge.",
    parameters=WebSearchArgs,
    func=web_search,
)

reasoning_tool = WikiTool(
    name="deep_reasoning",
    description="For complex reasoning or drafting longer texts with a lot of context. Optional: vault paths whose content is automatically sent along as context.",
    parameters=ReasoningArgs,
    func=run_reasoning,
)

__all__ = [
    "ask_librarian_tool",
    "web_search_tool",
    "reasoning_tool",
]
