# src/agentic/engine/response.py
"""Hilfsfunktionen für die Verarbeitung und Bereinigung von LLM-Antworten."""


def strip_json_fence(text: str) -> str:
    """Entfernt eine umschließende Markdown-Codeblock-Klammer (```json ... ```),
    falls das Modell trotz Anweisung eine liefert. Nur relevant, wenn kein
    response_format erzwungen wird (also im Tool-Calling-Fall), ansonsten ein No-Op."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[1] if "\n" in text else ""
    if body.endswith("```"):
        body = body[:-3]
    return body.strip()
