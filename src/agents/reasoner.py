# src/agents/reasoner.py
"""Denk-/Ausarbeitungs-Agent für komplexe Überlegungen und das Ausformulieren längerer
Texte mit viel Kontext. Läuft, wie der Websuche-Agent (web_search.py), NICHT
über litellm/WikiAgent/AgentSession, sondern nutzt das Google Antigravity SDK direkt für
einen einzelnen, nicht-multiturn Aufruf. Ist nur als Tool des Chat-Agenten gedacht: Pfade
zu Wiki-Dateien können mitgegeben werden, deren Inhalt dann als Kontext in den Prompt
eingebettet wird."""
import asyncio
import os

from google.antigravity import Agent, LocalAgentConfig, models, types

from src.core.logging_config import logger
from src.navigation import load_files

MODEL = "gemini-3.6-flash"  # unterstützt erweitertes Thinking (ThinkingLevel) über dieses SDK

SYSTEM_INSTRUCTIONS = """Du bist der Denk- und Ausarbeitungs-Agent eines persönlichen
Science-Fiction-Weltenbau-Wikis. Du wirst für Aufgaben eingesetzt, die viel Kontext und
gründliches Nachdenken brauchen statt einer schnellen Antwort: komplexe gedankliche
Ausarbeitungen (z.B. wie ein neues Konzept konsistent in die bestehende Welt passt,
Konsequenzen zu Ende denken, Widersprüche aufspüren) oder das Ausformulieren längerer,
kohärenter Texte auf Basis von gegebenem Kontext.

Du bekommst die eigentliche Aufgabe sowie optional den Inhalt relevanter Wiki-Dateien als
Kontext. Behandle diesen Kontext als verlässliche Quelle über das Universum – erfinde
keine Fakten, die ihm widersprechen, aber ergänze/formuliere gerne aus, wo die Aufgabe das
verlangt. Du kennst sonst nichts über das Universum außer dem, was dir hier mitgegeben
wird.

Arbeite gründlich und in der Tiefe, die die Aufgabe verlangt, und liefere direkt das
Ergebnis (die ausgearbeitete Antwort bzw. den ausformulierten Text) – keine Rückfragen,
keine Meta-Kommentare über die Aufgabe selbst."""


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
        # Reiner Text-Aufruf: keine Agenten-Werkzeuge (Dateisystem, Shell, Websuche, ...)
        # anbieten, das hier ist kein autonomer Coding-/Browsing-Agent. workspaces=[]
        # verhindert zusätzlich, dass der Harness einen lokalen Arbeitsordner-Kontext
        # (und damit absolute Host-Pfade) in die Antwort einstreut.
        capabilities=types.CapabilitiesConfig(enabled_tools=[]),
        workspaces=[],
        system_instructions=SYSTEM_INSTRUCTIONS,
    )


async def _run_reasoning_async(task: str, file_paths: list[str]) -> str:
    context_block = ""
    if file_paths:
        context_block = "\n\n## Kontext aus dem Wiki\n\n" + load_files(file_paths)

    async with Agent(_build_config()) as agent:
        response = await agent.chat(f"{task}{context_block}")
        return (await response.text()).strip()


def run_reasoning(task: str, file_paths: list[str] | None = None) -> str:
    """Führt eine einzelne, nicht-multiturn Denk-/Ausarbeitungsanfrage aus (z.B. als
    Tool des Chat-Agenten). Gibt bei Fehlern einen les- und nutzbaren Fehlertext statt
    einer Exception zurück, damit ein aufrufender Agent das Ergebnis direkt als
    Tool-Antwort verwenden kann."""
    try:
        text = asyncio.run(_run_reasoning_async(task, file_paths or []))
    except Exception as e:
        logger.error(f"[Reasoner] Antigravity-Aufruf fehlgeschlagen: {e}")
        return f"Fehler: Der Denk-Agent konnte die Aufgabe nicht bearbeiten ({e})."

    if not text:
        logger.warning("[Reasoner] Leere Antwort vom Antigravity-Agenten erhalten.")
        return "Fehler: Der Denk-Agent lieferte keine Antwort."

    logger.info("[Reasoner] Aufgabe bearbeitet.")
    return text
