# src/agentic/engine/compaction.py
"""Kontext-Kompaktierung für lange ReAct-Sessions (v.a. den Task-Agenten): Lange,
vielschrittige Sessions sammeln pro Runde neue Tool-Aufrufe/-Ergebnisse an, und weil bei
jedem LLM-Aufruf der KOMPLETTE bisherige Verlauf erneut gesendet wird (siehe
AgentSession.build_messages), wächst die tatsächlich verbrauchte Tokenmenge über viele
Runden hinweg quadratisch – ein einzelner großer Tool-Aufruf (z.B. eine per create_file
neu geschriebene Datei) wird sonst bei jeder weiteren Runde erneut mitgeschickt, obwohl
er längst erledigt und auf der Platte ist.

Diese Funktion ersetzt bei Bedarf den ÄLTEREN Teil des Verlaufs (alles außer
System-Prompt, erster Aufgaben-Nachricht und den letzten paar ReAct-Runden) durch eine
knappe, per günstigem LLM erzeugte Zusammenfassung. Wird von llm_engine._run_turn nach
abgeschlossenen ReAct-Runden aufgerufen, wenn agent.enable_context_compaction gesetzt ist.
"""
import json

import litellm

from src.core.logging_config import logger
from src.schemas.agent_schema import AgentSession, MessageRole, SessionMessage
from src.schemas.llm_models import LLMModels

COMPACTION_SYSTEM_PROMPT = """Du fasst den bisherigen Arbeitsverlauf eines Agenten zusammen, der eigenständig an
einer Aufgabe arbeitet (Tool-Aufrufe, Ergebnisse, Zwischenstände). Deine Zusammenfassung ERSETZT den
Original-Verlauf im Kontext des Agenten – er muss danach ohne die Originaldaten weiterarbeiten können.

Erhalte alle Fakten, die für die WEITERE Arbeit noch relevant sein könnten:
- Was wurde bereits konkret getan (z.B. welche Dateien mit welchem Ergebnis erstellt/geändert/verschoben)?
- Welche Vault-Pfade sind entstanden oder betroffen?
- Welche wichtigen Inhalte/Fakten wurden recherchiert (kurz, aber konkret – Namen, Werte, Zusammenhänge)?
- Aktueller Stand/Fortschritt, offene Punkte.

Lass technisches Rauschen weg (rohe Tool-Aufruf-Syntax, vollständige Dateiinhalte, die bereits geschrieben
und nicht mehr gebraucht werden). Schreibe dicht und stichworthaltig, keine Prosa-Nacherzählung. Antworte
NUR mit der Zusammenfassung, ohne Einleitung."""


def _round_start_indices(messages: list[SessionMessage]) -> list[int]:
    """Jede ASSISTANT-Nachricht startet in unserem Protokoll eine neue ReAct-Runde
    (Tool-Call-Runde oder finale Antwort). Nur an diesen Indizes darf geschnitten
    werden, sonst würde ein Tool-Ergebnis von seinem Tool-Aufruf getrennt."""
    return [i for i, m in enumerate(messages) if m.role == MessageRole.ASSISTANT]


def _format_for_compaction(messages: list[SessionMessage]) -> str:
    lines = []
    for m in messages:
        if m.role == MessageRole.ASSISTANT and m.tool_calls:
            calls = ", ".join(f"{tc.tool_name}({tc.arguments})" for tc in m.tool_calls)
            lines.append(f"[ASSISTANT ruft auf] {calls}")
        elif m.role == MessageRole.TOOL:
            lines.append(f"[TOOL-ERGEBNIS ({m.tool_name})] {m.content}")
        else:
            lines.append(f"[{m.role.value.upper()}] {m.content}")
    return "\n\n".join(lines)


def context_size_chars(session: AgentSession) -> int:
    """Größe des tatsächlich gesendeten Kontexts. Wichtig: bei ASSISTANT-Nachrichten mit
    Tool-Calls stecken die eigentlichen Nutzdaten (z.B. der komplette neue Dateiinhalt
    bei create_file) in tool_calls[].arguments, NICHT in .content – die müssen mitgezählt
    werden, sonst wird der dominante Kostentreiber aus der Praxis systematisch übersehen."""
    total = 0
    for m in session.messages:
        total += len(m.content or "")
        for tc in m.tool_calls:
            total += len(json.dumps(tc.arguments, ensure_ascii=False))
    return total


def maybe_compact(session: AgentSession, step: int, session_logger) -> None:
    """Prüft, ob der aktuelle Kontext die Schwelle des Agenten überschreitet, und
    verdichtet ihn falls nötig. No-Op, wenn Kompaktierung deaktiviert ist, der Kontext
    noch klein genug ist, oder noch nicht genug Runden für einen sicheren Schnitt
    vorhanden sind. Fehler beim Verdichten sind nicht fatal – der Kontext bleibt dann
    einfach unverändert, die Session läuft normal weiter."""
    agent = session.agent
    if not agent.enable_context_compaction:
        return

    before_chars = context_size_chars(session)
    if before_chars < agent.compaction_threshold_chars:
        return

    head = session.messages[:2]  # System-Prompt + erste Aufgaben-Nachricht, bleiben immer erhalten
    rest = session.messages[2:]

    round_starts = _round_start_indices(rest)
    keep_rounds = agent.compaction_keep_recent_rounds
    if len(round_starts) <= keep_rounds:
        return  # noch nicht genug abgeschlossene Runden für einen sicheren Schnitt

    cut_index = round_starts[-keep_rounds]
    to_compact, recent = rest[:cut_index], rest[cut_index:]
    if not to_compact:
        return

    transcript = _format_for_compaction(to_compact)

    try:
        response = litellm.completion(
            model=agent.compaction_model,
            messages=[
                {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
        )
        summary = (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error(f"[Compaction] Zusammenfassung fehlgeschlagen, Kontext bleibt unverändert: {e}")
        return

    if not summary:
        logger.warning("[Compaction] Leere Zusammenfassung erhalten, Kontext bleibt unverändert.")
        return

    summary_message = SessionMessage(
        role=MessageRole.USER,
        content=f"[Zusammenfassung des bisherigen Verlaufs, {len(to_compact)} Nachrichten verdichtet]\n\n{summary}",
    )
    session.messages = head + [summary_message] + recent
    after_chars = context_size_chars(session)

    logger.info(
        f"[Compaction] {agent.name}: {len(to_compact)} Nachrichten verdichtet "
        f"({before_chars} -> {after_chars} Zeichen)."
    )
    session_logger.log_compaction(step, before_chars, after_chars, len(to_compact), summary)
