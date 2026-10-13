# src/agentic/agents/reasoner.py
"""Reasoning/drafting agent for complex considerations and for drafting longer texts
with a lot of context. Like the web search agent (web_search.py), it does NOT run
through litellm/WikiAgent/AgentSession, but uses the Google Antigravity SDK directly for
a single, non-multiturn call. It is intended only as a tool of the chat agent: vault
file paths can be passed along, whose content is then embedded into the prompt as
context."""
import asyncio
import os

from google.antigravity import Agent, LocalAgentConfig, models, types

from src.core.logging_config import logger
from src.navigation import load_files

MODEL = "gemini-3.6-flash"  # supports extended thinking (ThinkingLevel) through this SDK

SYSTEM_INSTRUCTIONS = """You are the reasoning and drafting agent of a personal Obsidian
knowledge vault. You are used for tasks that need a lot of context and careful thought
rather than a quick answer: complex reasoning (e.g. how a new concept fits consistently
into what already exists, thinking consequences through, spotting contradictions) or
drafting longer, coherent texts on the basis of given context.

You receive the actual task and, optionally, the content of relevant vault files as
context. Treat that context as the reliable source about the subject matter - do not
invent facts that contradict it, but do feel free to extend and elaborate where the task
calls for it. You know nothing else about the subject beyond what is given to you here.

Work thoroughly and to the depth the task requires, and deliver the result directly (the
worked-out answer or the drafted text) - no follow-up questions, no meta-commentary about
the task itself."""


def _build_config() -> LocalAgentConfig:
    api_key = os.environ.get("GEMINI_API_KEY")
    return LocalAgentConfig(
        api_key=api_key,
        model=models.ModelTarget(
            name=MODEL,
            endpoint=models.GeminiAPIEndpoint(
                api_key=api_key,
                options=models.GeminiModelOptions(thinking_level=models.ThinkingLevel.HIGH),
            ),
        ),
        # Pure text call: offer no agent tools (filesystem, shell, web search, ...) -
        # this is not an autonomous coding/browsing agent. workspaces=[] additionally
        # prevents the harness from sprinkling a local working-directory context (and
        # with it absolute host paths) into the response.
        capabilities=types.CapabilitiesConfig(enabled_tools=[]),
        workspaces=[],
        system_instructions=SYSTEM_INSTRUCTIONS,
    )


async def _run_reasoning_async(task: str, file_paths: list[str]) -> str:
    context_block = ""
    if file_paths:
        context_block = "\n\n## Context from the vault\n\n" + load_files(file_paths)

    async with Agent(_build_config()) as agent:
        response = await agent.chat(f"{task}{context_block}")
        return (await response.text()).strip()


def run_reasoning(task: str, file_paths: list[str] | None = None) -> str:
    """Runs a single, non-multiturn reasoning/drafting request (e.g. as a tool of the
    chat agent). On failure it returns readable, usable error text instead of raising,
    so a calling agent can use the result directly as a tool response."""
    try:
        text = asyncio.run(_run_reasoning_async(task, file_paths or []))
    except Exception as e:
        logger.error(f"[Reasoner] Antigravity call failed: {e}")
        return f"Error: the reasoning agent could not process the task ({e})."

    if not text:
        logger.warning("[Reasoner] Received an empty response from the Antigravity agent.")
        return "Error: the reasoning agent returned no answer."

    logger.info("[Reasoner] Task processed.")
    return text
