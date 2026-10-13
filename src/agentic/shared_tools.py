# src/agents/shared_tools.py
"""Zustandslose WikiTool-Instanzen, die mehrere Agenten gemeinsam nutzen (aktuell:
Chat-Agent und Task-Agent). Liegen in einem eigenen Modul statt in chat.py, damit
task_agent.py sie importieren kann, ohne einen Kreisimport mit chat.py zu erzeugen
(chat.py importiert umgekehrt Funktionen aus task_agent.py für seine eigenen
Hintergrund-Task-Werkzeuge)."""
from src.schemas.chat_schema import AskLibrarianArgs, CreateDirectoryArgs, CreateFileArgs, EditFileArgs, MoveFileArgs, DeleteFileArgs
from src.schemas.reasoner_schema import ReasoningArgs
from src.schemas.tool_schema import WikiTool
from src.schemas.web_search_schema import WebSearchArgs
from src.agentic.agents.librarian import ask_librarian, files_tool
from src.agentic.agents.reasoner import run_reasoning
from src.agentic.agents.web_search import web_search
from src.navigation import create_directory, create_file, edit_file, load_files, move_file, delete_file


def _ask_librarian_tool(question: str) -> str:
    result = ask_librarian(question)
    if not result.is_successful:
        return "Fehler: Der Librarian konnte zu dieser Frage keine Antwort recherchieren."
    output = result.final_result

    if not output.sources:
        return f"{output.answer}\n\nQuellen: (keine)"

    # Die vom Librarian zitierten Quellen-Dateien direkt im Volltext mitliefern, damit
    # der aufrufende Agent sie nicht noch per load_files nachladen muss.
    return (
        f"{output.answer}\n\nQuellen: {', '.join(output.sources)}"
        f"\n\n## Volltext der zitierten Quellen\n\n{load_files(output.sources)}"
    )


ask_librarian_tool = WikiTool(
    name="ask_librarian",
    description="Stellt dem Librarian-Agenten eine Recherche-Frage zum Vault-Inhalt und liefert dessen mit Quellen belegte Antwort zurück.",
    parameters=AskLibrarianArgs,
    func=_ask_librarian_tool,
)

web_search_tool = WikiTool(
    name="web_search",
    description="Recherchiert per echter Websuche im realen Internet (nicht der Vault) – für Realismus-/Faktenchecks von Universum-Konzepten und für allgemeine Fragen, die aktuelles Weltwissen brauchen.",
    parameters=WebSearchArgs,
    func=web_search,
)

reasoning_tool = WikiTool(
    name="deep_reasoning",
    description="Für komplexe Überlegungen oder das Ausformulieren längerer Texte mit viel Kontext. Optional: Vault-Pfade, deren Inhalt automatisch als Kontext mitgeschickt wird.",
    parameters=ReasoningArgs,
    func=run_reasoning,
)

create_directory_tool = WikiTool(
    name="create_directory",
    description="Legt einen neuen (leeren) Ordner im Vault an, inkl. fehlender Zwischenordner.",
    parameters=CreateDirectoryArgs,
    func=create_directory,
)

create_file_tool = WikiTool(
    name="create_file",
    description="Legt eine neue .md-Datei mit dem gegebenen Inhalt im Vault an (Pfad darf noch nicht existieren).",
    parameters=CreateFileArgs,
    func=create_file,
)

move_file_tool = WikiTool(
    name="move_file",
    description="Verschiebt/benennt eine bestehende Datei im Vault um (Zielpfad darf noch nicht existieren).",
    parameters=MoveFileArgs,
    func=move_file,
)

edit_file_tool = WikiTool(
    name="edit_file",
    description="Ersetzt den Inhalt einer BESTEHENDEN .md-Datei im Vault (Frontmatter bleibt erhalten). Für Änderungen an vorhandenen Dateien - NICHT move_file+create_file kombinieren.",
    parameters=EditFileArgs,
    func=edit_file,
)

delete_file_tool = WikiTool(
    name="delete_file",
    description="Löscht eine bestehende .md-Datei im Vault dauerhaft.",
    parameters=DeleteFileArgs,
    func=delete_file,
)

# Die "Standard-Fähigkeiten", die sowohl Chat- als auch Task-Agent bekommen (jeweils
# noch ergänzt um agenten-spezifische Werkzeuge wie load_files/files_tool oder
# update_plan/Hintergrund-Task-Steuerung).
CONTENT_TOOLS = [
    files_tool,
    ask_librarian_tool,
    web_search_tool,
    reasoning_tool,
    create_directory_tool,
    create_file_tool,
    edit_file_tool,
    move_file_tool,
    delete_file_tool,
]
