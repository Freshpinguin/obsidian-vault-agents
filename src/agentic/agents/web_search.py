# src/agents/web_search.py
"""Websuche-Agent: recherchiert per echter Google-Websuche (Search Grounding) im realen
Internet – für alles, was NICHT im Vault steht: sowohl Realismus-/Faktenchecks von
Konzepten aus dem Universum als auch ganz allgemeine Fragen, die aktuelles Wissen aus der
echten Welt brauchen. Anders als die übrigen Agenten läuft er NICHT über
litellm/WikiAgent/AgentSession – er ist bewusst nicht multiturn und hat kein eigenes
ReAct-Tool-Set, sondern ist selbst nur als einzelner Aufruf gedacht, den z.B. der
Chat-Agent als Tool nutzt."""
from google import genai
from google.genai import types

from src.core.logging_config import logger

AGENT = "antigravity-preview-09-2026"
MODEL = "gemini-3.5-flash-lite"
AGENT_CONFIG = {
    "type": "antigravity",
    "model": MODEL,
}

SYSTEM_INSTRUCTION = """Du bist der Websuche-Agent eines persönlichen Science-Fiction-Weltenbau-Wikis.

Du beantwortest Anfragen, die eine echte, aktuelle Websuche brauchen – der Vault selbst kennt so etwas
nicht, das ist ausschließlich dein Zuständigkeitsbereich. Zwei typische Arten von Anfragen:

1. Realismus-/Faktenchecks von Konzepten aus dem fiktiven Universum: Du bekommst die Beschreibung eines
   Konzepts, einer Technologie oder eines Phänomens aus dem Universum und recherchierst, wie es sich zum
   aktuellen realen wissenschaftlichen/technischen Kenntnisstand verhält – was davon realistisch ist bzw.
   worauf es beruht (reale Physik, existierende/erforschte Technologien, echte Theorien), was spekulativ
   oder (noch) nicht erreicht ist, und ob es reale Forschung/Experimente gibt, die dem nahekommen. Ziel ist
   NICHT, das Weltenbau-Konzept "richtig" oder "falsch" zu bewerten – Science-Fiction darf von der Realität
   abweichen. Ziel ist, verlässliche aktuelle Fakten zu liefern, anhand derer sich die Distanz zur Realität
   einschätzen lässt.

2. Allgemeine Fragen, die aktuelles Wissen aus der echten Welt brauchen und nicht aus dem Vault-Inhalt
   beantwortbar sind (z.B. aktuelle Ereignisse, reale Fakten, Definitionen, Vergleichswerte) – hier
   recherchierst du ganz normal die Antwort auf die gestellte Frage.

In beiden Fällen: Liefere eine kompakte, sachliche Antwort und stütze dich ausschließlich auf das, was
deine Websuche tatsächlich findet – erfinde nichts, was die Suche nicht hergibt."""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()  # liest GEMINI_API_KEY aus der Umgebung
    return _client


def _extract_sources(response) -> list[str]:
    """Sammelt die über Search Grounding tatsächlich verwendeten Quellen (Titel + URL)."""
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
    """Beantwortet eine einzelne Anfrage per Google Interactions API (Realismus-Check
    eines Konzepts ODER allgemeine Wissensfrage) und gibt die gefundenen Details (inkl.
    Quellen) als Text zurück. Gibt bei Fehlern einen les- und nutzbaren Fehlertext statt
    einer Exception zurück, damit ein aufrufender Agent das Ergebnis direkt als
    Tool-Antwort verwenden kann."""
    prompt = f"{SYSTEM_INSTRUCTION}\n\nAnfrage:\n{query}"

    try:
        interaction = _get_client().interactions.create(
            agent=AGENT,
            input=prompt,
            environment="remote",
            agent_config=AGENT_CONFIG,
        )
    except Exception as e:
        logger.error(f"[WebSearch] Interactions-Aufruf fehlgeschlagen: {e}")
        return f"Fehler: Die Websuche konnte nicht durchgeführt werden ({e})."

    text = (
        getattr(interaction, "output_text", None)
        or getattr(interaction, "text", None)
        or ""
    ).strip()
    if not text:
        logger.warning("[WebSearch] Leere Antwort von Interactions erhalten.")
        return "Fehler: Die Websuche lieferte keine Antwort."

    sources = _extract_sources(interaction)
    if sources:
        text += "\n\nQuellen:\n" + "\n".join(f"- {s}" for s in sources)

    logger.info(f"[WebSearch] Anfrage bearbeitet.")
    return text
