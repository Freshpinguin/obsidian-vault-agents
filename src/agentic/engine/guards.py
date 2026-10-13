# src/agentic/engine/guards.py
"""Schutzmechanismen und Halluzinations-Erkennung für die Agent-ReAct-Schleife."""
from typing import Any
from src.schemas.status import AgentStatus
from src.schemas.tool_schema import MUTATION_TOOL_NAMES

MUTATION_INDICATORS = [
    "angelegt", "erstellt", "gespeichert", "bearbeitet", "verschoben", "gelöscht",
    "lege dir", "erstelle dir", "lege die datei", "erstelle die datei",
    "ich erstelle", "ich lege", "lösche die datei", "habe gelöscht",
]

NEGATIONS = [
    "nicht angelegt", "keine datei", "konnte nicht", "nicht möglich",
    "nicht gefunden", "wurde nicht", "nicht gelöscht",
]

SKIPPED_REQUIRED_TOOL_ERROR = (
    "Deine Antwort wurde abgelehnt: Du musst für diese Aufgabe mindestens einmal ein Werkzeug "
    "aufrufen (z.B. update_plan), bevor du eine finale Antwort gibst. Rufe jetzt zuerst das "
    "passende Werkzeug auf, statt direkt zu antworten."
)

HALLUCINATED_MUTATION_ERROR = (
    "Deine Antwort wurde abgelehnt: Du hast im Antworttext behauptet oder angekündigt, eine Datei bzw. einen Ordner "
    "anzulegen oder zu verändern, hast aber KEIN entsprechendes Werkzeug (z.B. create_file, edit_file) "
    "als Tool-Call ausgeführt! Es wurde daher nichts im Vault gespeichert. "
    "Rufe JETZT im nächsten Schritt ZUERST das passende Werkzeug (z.B. create_file) per Function-Call auf!"
)


def check_skipped_required_tool(agent: Any, tool_steps: int) -> bool:
    """Modell hat den geforderten 'erst mindestens ein Tool nutzen'-Schritt übersprungen
    und direkt eine (evtl. komplett halluzinierte) finale Antwort geliefert - trotz
    gültigem JSON NICHT als Erfolg werten, sondern wie einen Parse-Fehler behandeln."""
    return bool(getattr(agent, "require_tool_call_first_round", False) and tool_steps == 0)


def check_hallucinated_mutation(agent: Any, parse_result: Any, tool_steps: int) -> bool:
    """Prüft, ob der Agent eine Dateimodifikation im Text behauptet/angekündigt hat,
    ohne je ein entsprechendes Werkzeug (z.B. create_file, edit_file) aufgerufen zu haben."""
    if tool_steps != 0:
        return False

    status = getattr(parse_result, "status", None)
    if status != AgentStatus.SUCCESS:
        return False

    agent_tools = getattr(agent, "tools", []) or []
    has_mutation_tools = any(getattr(t, "name", None) in MUTATION_TOOL_NAMES for t in agent_tools)
    if not has_mutation_tools:
        return False

    reply_text = ""
    parsed_data = getattr(parse_result, "parsed_data", None)
    if hasattr(parsed_data, "reply"):
        reply_text = str(parsed_data.reply).lower()
    elif isinstance(parsed_data, dict):
        reply_text = str(parsed_data.get("reply", "")).lower()

    if any(ind in reply_text for ind in MUTATION_INDICATORS) and (
        ".md" in reply_text or "datei" in reply_text or "ordner" in reply_text
    ):
        if not any(neg in reply_text for neg in NEGATIONS):
            return True

    return False
