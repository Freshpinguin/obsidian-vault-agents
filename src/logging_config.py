import logging
from logging.handlers import RotatingFileHandler
import os
import glob
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.schemas.agent_schema import AgentSession, LLMCall

# Basis-Ordner für Logs definieren
LOG_DIR = os.getenv("LOG_DIR", "logs")
LLM_DIR = os.path.join(LOG_DIR, "llm_details")

# Ordner erstellen, falls sie nicht existieren
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(LLM_DIR, exist_ok=True)

# Wie viele Session-Logdateien maximal aufbewahrt werden
MAX_SESSION_LOGS = 100

# ==========================================
# 1. Main Logger Setup (Rolling)
# ==========================================
logger = logging.getLogger("scifi_engine")
logger.setLevel(logging.INFO)

# Verhindern, dass Logs doppelt ausgegeben werden
if not logger.handlers:
    # Konsolen-Ausgabe (optional, aber hilfreich beim Entwickeln)
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Datei-Ausgabe (Rolling: max 5MB pro Datei, max 5 Backups)
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "engine.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)


# ==========================================
# 2. Granulares LLM Detail-Logging: EIN Logfile pro AgentSession
# ==========================================
def _cleanup_old_session_logs():
    """Behält nur die letzten MAX_SESSION_LOGS Session-Logdateien."""
    files = sorted(glob.glob(os.path.join(LLM_DIR, "*.md")), key=os.path.getmtime)
    while len(files) > MAX_SESSION_LOGS:
        oldest_file = files.pop(0)
        try:
            os.remove(oldest_file)
        except Exception as e:
            logger.error(f"Konnte altes Session-Log {oldest_file} nicht löschen: {e}")


class SessionLogger:
    """Sammelt den gesamten Verlauf einer AgentSession (jeder LLM-Turn, jeder
    Tool-Aufruf) in einer einzigen Markdown-Logdatei, statt wie zuvor pro LLM-Call
    eine eigene Datei zu erzeugen. Die Datei wird bei Session-Start angelegt und bei
    jedem Turn per Append fortgeschrieben, damit auch bei einem Absturz mitten in
    einer langen ReAct-Schleife bereits alles bis dahin auf der Platte steht.

    Für Chat-Agenten, bei denen dieselbe Session über mehrere Nutzer-Nachrichten
    hinweg weiterlebt, wird über 'existing_path' an dieselbe Datei angeknüpft statt
    bei jeder neuen Nachricht eine weitere Datei anzulegen – eine Session bleibt so
    IMMER genau eine Logdatei, unabhängig davon, wie viele Turns sie hat.
    """

    def __init__(self, agent_name: str, session_id: str, existing_path: str | None = None):
        if existing_path and os.path.exists(existing_path):
            self.filepath = existing_path
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(LLM_DIR, f"{timestamp}_{agent_name}_{session_id}.md")

        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(f"# Agent Session: {agent_name} ({session_id})\n\n")
            f.write(f"**Gestartet:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n")

        _cleanup_old_session_logs()

    def log_step(self, step: int, call: "LLMCall", messages: list[dict], model: str, raw_response: str, tokens_in: int, tokens_out: int):
        """Protokolliert einen LLM-Turn: den vollständigen zu diesem Zeitpunkt gesendeten
        Kontext (aus der Session zusammengesetzt), die rohe Modellantwort sowie ggf.
        ausgeführte Tool-Aufrufe mit ihrem Ergebnis. 'step' zählt fortlaufend über die
        gesamte Session (nicht nur den aktuellen Turn), damit die Nummerierung auch bei
        Chat-Sessions mit mehreren Nachrichten eindeutig bleibt."""
        prompt_text = "\n\n".join(
            f"[{m['role'].upper()}]\n{m.get('content') or ''}" for m in messages
        )

        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"## Schritt {step} — {model} — {call.status.upper()}\n\n")
            f.write(f"**Tokens In:** {tokens_in} | **Tokens Out:** {tokens_out}\n\n")
            f.write(f"### Kontext (kompletter Verlauf bis zu diesem Turn)\n\n{prompt_text}\n\n")
            f.write(f"### Rohe Antwort\n\n{raw_response}\n\n")
            if call.tool_calls:
                f.write("### Tool-Aufrufe\n\n")
                for tc in call.tool_calls:
                    f.write(f"- **{tc.tool_name}**(`{tc.arguments}`)\n\n  → {tc.result}\n\n")
            f.write("---\n\n")

    def log_api_error(self, step: int, model: str, messages: list[dict], error: str):
        prompt_text = "\n\n".join(
            f"[{m['role'].upper()}]\n{m.get('content') or ''}" for m in messages
        )
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"## Schritt {step} — {model} — API FEHLER\n\n")
            f.write(f"### Kontext (kompletter Verlauf bis zu diesem Turn)\n\n{prompt_text}\n\n")
            f.write(f"### Fehler\n\n{error}\n\n---\n\n")

    def log_compaction(self, step: int, before_chars: int, after_chars: int, compacted_count: int, summary: str):
        """Protokolliert eine Kontext-Verdichtung (siehe context_compactor.py) – wichtig
        für die Nachvollziehbarkeit, da der Kontext, den das Modell ab hier tatsächlich
        sieht, sich vom vorherigen Schritt unterscheidet."""
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(f"## Kontext-Verdichtung vor Schritt {step}\n\n")
            f.write(f"{compacted_count} Nachrichten verdichtet: {before_chars} -> {after_chars} Zeichen.\n\n")
            f.write(f"### Zusammenfassung\n\n{summary}\n\n---\n\n")

    def log_turn_end(self, session: "AgentSession"):
        """Schreibt eine Zwischenbilanz ans Ende der Logdatei – bei Ein-Schritt-Agenten
        der endgültige Abschluss, bei Chat-Agenten der Stand nach dem aktuellen Turn
        (die Datei läuft danach beim nächsten Turn einfach weiter)."""
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write("## Ergebnis (bisheriger Stand)\n\n")
            f.write("✅ Letzter Turn erfolgreich\n" if session.is_successful else "❌ Letzter Turn fehlgeschlagen\n")
            f.write(f"\nTurns gesamt: {len(session.history)} | davon Tool-Aufrufe: {session.tool_steps}\n\n---\n\n")
