# src/agentic/agents/web_search.py
"""Web search agent: researches via a real Google web search (Search grounding) on the
live internet - for everything NOT in the vault: both fact-checking vault concepts
against reality and entirely general questions that need current real-world knowledge.
Unlike the other agents it does NOT run through litellm/WikiAgent/AgentSession - it is
deliberately not multi-turn and has no ReAct tool set of its own, but is itself intended
only as a single call, used as a tool by e.g. the chat agent."""
from google import genai
from google.genai import types

from src.core.logging_config import logger

AGENT = "antigravity-preview-09-2026"
MODEL = "gemini-3.5-flash-lite"
AGENT_CONFIG = {
    "type": "antigravity",
    "model": MODEL,
}

SYSTEM_INSTRUCTION = """You are the web search agent of a personal Obsidian knowledge vault.

You answer queries that need a real, current web search - the vault itself knows nothing of that kind, it
is exclusively your area of responsibility. Two typical kinds of query:

1. Fact-checking or plausibility-checking concepts from the vault against reality: you receive the
   description of a concept, technology or phenomenon from the vault and research how it relates to the
   current state of real scientific and technical knowledge - what about it is realistic or what it rests
   on (real physics, existing or researched technologies, actual theories), what is speculative or not
   (yet) achieved, and whether there is real research or experiments that come close to it. The goal is NOT
   to judge the concept "right" or "wrong" - a vault's content may legitimately depart from reality. The
   goal is to supply reliable current facts from which the distance to reality can be judged.

2. General questions that need current real-world knowledge and are not answerable from the vault content
   (e.g. current events, real-world facts, definitions, reference values) - here you simply research the
   answer to the question as asked.

In both cases: deliver a compact, factual answer and rely exclusively on what your web search actually
finds - do not invent anything the search does not support."""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()  # reads GEMINI_API_KEY from the environment
    return _client


def _extract_sources(response) -> list[str]:
    """Collects the sources actually used via Search grounding (title + URL)."""
    sources: list[str] = []
    seen: set[str] = set()
    for candidate in getattr(response, "candidates", None) or []:
        metadata = getattr(candidate, "grounding_metadata", None)
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None)
            if not uri or uri in seen:
                continue
            seen.add(uri)
            sources.append(f"{getattr(web, 'title', None) or uri} ({uri})")
    return sources


def web_search(query: str) -> str:
    """Answers a single query via the Google Interactions API (a reality check of a
    concept OR a general knowledge question) and returns the details found (including
    sources) as text. On failure it returns readable, usable error text instead of
    raising, so a calling agent can use the result directly as a tool response."""
    prompt = f"{SYSTEM_INSTRUCTION}\n\nQuery:\n{query}"

    try:
        interaction = _get_client().interactions.create(
            agent=AGENT,
            input=prompt,
            environment="remote",
            agent_config=AGENT_CONFIG,
        )
    except Exception as e:
        logger.error(f"[WebSearch] Interactions call failed: {e}")
        return f"Error: the web search could not be performed ({e})."

    text = (
        getattr(interaction, "output_text", None)
        or getattr(interaction, "text", None)
        or ""
    ).strip()
    if not text:
        logger.warning("[WebSearch] Received an empty response from Interactions.")
        return "Error: the web search returned no answer."

    sources = _extract_sources(interaction)
    if sources:
        text += "\n\nSources:\n" + "\n".join(f"- {s}" for s in sources)

    logger.info("[WebSearch] Query processed.")
    return text
