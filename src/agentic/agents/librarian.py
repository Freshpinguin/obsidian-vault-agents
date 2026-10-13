# src/agents/librarian.py
import itertools
import threading
from typing import Any

from src.schemas.agent_schema import AgentSession, WikiAgent
from src.schemas.librarian_schema import LibrarianInput, LibrarianOutput
from src.schemas.llm_models import LLMModels
from src.agentic.engine import run_agent_session
from src.agentic.tools.vault_read import (
    directory_summaries_tool,
    file_summaries_tool,
    files_tool,
)
from src.navigation import (
    load_ai_map,
    format_ai_map,
)

SYSTEM_PROMPT = """Du bist der Librarian-Agent eines persönlichen Obsidian-Wikis (Science-Fiction-Weltenbau).
Deine Aufgabe: Fragen zum Inhalt des Vaults präzise und mit Belegen beantworten.

Du bekommst mit der Anfrage bereits die komplette Vault-Übersicht (ai_map): eine Liste aller Ordner und
Dateien mit ihrer jeweiligen Kurz-Zusammenfassung. Das ist dein Ausgangspunkt für die Recherche – du musst
sie nicht erneut abrufen, sie liegt dir schon vor.

Für die eigentliche Recherche stehen dir drei Werkzeuge zur Verfügung:
- load_directory_summaries(paths): ausführliche Zusammenfassung von Ordnern (inkl. Datei-/Unterordnerliste
  mit Kurz-Zusammenfassung) – nützlich, um dich innerhalb eines Themas zu orientieren.
- load_file_summaries(paths): die Kurz-Zusammenfassung einzelner Dateien.
- load_files(paths): der VOLLE Inhalt einzelner Dateien – die einzige verlässliche Quelle für Details, Zahlen,
  Namen und Zitate. Zusammenfassungen (in der ai_map, in Ordner- oder Datei-Zusammenfassungen) dienen nur der
  Navigation, nicht als Beleg für deine Antwort.

WICHTIG für Geschwindigkeit: Alle drei Werkzeuge nehmen eine LISTE von Pfaden entgegen. Frage IMMER alle
Pfade, die du für plausibel hältst, in einem einzigen Aufruf ab, statt sie einzeln nacheinander zu laden. Du
kannst außerdem in einer einzigen Antwort mehrere Werkzeuge gleichzeitig aufrufen (z.B. load_files für zwei
Kandidaten und parallel load_directory_summaries für einen dritten Ordner) – nutze das aktiv, um Runden zu
sparen.

Geschwindigkeit hat Vorrang vor Gründlichkeit: Wenn die Frage einfach ist und die ai_map bereits klar auf
eine oder wenige Dateien zeigt, lade diese Dateien direkt per load_files und beantworte die Frage daraus –
ohne Umweg über Ordner-Zusammenfassungen. Erkunde nur dann tiefer (load_directory_summaries, mehrere
Datei-Zusammenfassungen, mehrere Suchrunden), wenn du unsicher bist, welche Datei gemeint ist, die ai_map
mehrdeutig ist oder du die richtige Datei auf Anhieb nicht findest.

Pfade müssen nicht exakt stimmen (Groß-/Kleinschreibung, Umlaute, Teilnamen werden toleriert); bei
mehrdeutigen Treffern bekommst du eine Liste der möglichen Kandidaten zurück und kannst gezielt nachfragen.

Es kann vorkommen, dass es zur Frage kein wirklich passendes Dokument im Vault gibt. Erfinde in diesem Fall
NICHTS: Sag in answer offen, dass du kein passendes Dokument gefunden hast, und liefere stattdessen als
nächstbeste Hilfe kurze Informationen zu den ähnlichsten Ordnern/Dateien, auf die du beim Suchen gestoßen
bist (Name + worum es dort laut Zusammenfassung geht), damit die Person selbst weitersuchen kann.

Sobald du genug gelesen hast, um die Frage zu beantworten (oder sicher bist, dass der Vault keine Antwort
enthält), rufe KEIN Werkzeug mehr auf und antworte stattdessen direkt im geforderten JSON-Format:

1. answer: Die eigentliche Antwort auf die Frage, gestützt auf den tatsächlich mit load_files gelesenen
   Inhalt (nicht nur auf Zusammenfassungen). Wenn der Vault die Frage nicht oder nur teilweise beantwortet,
   sag das explizit, statt etwas zu erfinden.
2. sources: Die Vault-Pfade genau der Dateien, auf denen die Antwort tatsächlich beruht (wie im
   Tool-Ergebnis angegeben, z.B. "Technologie/Militärtechnik/Waffen-Arsenal der Abfangjäger.md").
"""



LibrarianAgent = WikiAgent(
    name="Librarian",
    system_prompt=SYSTEM_PROMPT,
    input_type=LibrarianInput,
    response_type=LibrarianOutput,
    default_model=LLMModels.GEMMA_31B,
    tools=[directory_summaries_tool, file_summaries_tool, files_tool],
    max_tool_iterations=8,
)


from src.agentic.engine.model_rotation import LIBRARIAN_MODELS, librarian_rotation

# Free-Tier-APIs begrenzen Tokens/Minute PRO Modell. Ein einzelnes Modell (31B) läuft bei
# reger Nutzung schnell in dieses Limit; abwechselnd 31B/26B zu verwenden verteilt die Last
# auf zwei getrennte Kontingente.
_MODEL_ROTATION = LIBRARIAN_MODELS
_rotation = librarian_rotation


def _next_rotation_model() -> LLMModels:
    if hasattr(_rotation, "next"):
        return _rotation.next()
    return next(_rotation)


def ask_librarian(question: str, model_override: LLMModels | None = None) -> AgentSession:
    """Beantwortet eine Frage zum Vault-Inhalt über den Librarian-Agenten.
    Lädt die aktuelle ai_map und übergibt sie als Recherche-Ausgangspunkt. Ohne
    explizites model_override wechselt jeder Aufruf abwechselnd zwischen GEMMA_31B und
    GEMMA_26B, um das Tokens/Minute-Limit der Free-Tier-API auf zwei Modelle zu verteilen."""
    input_data = LibrarianInput(question=question, ai_map=format_ai_map(load_ai_map()))
    use_model = model_override or _next_rotation_model()
    return run_agent_session(agent=LibrarianAgent, raw_input=input_data, model_override=use_model)
