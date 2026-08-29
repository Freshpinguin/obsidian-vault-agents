# src/schemas/chat_schema.py
from pydantic import BaseModel, Field


class ChatInput(BaseModel):
    message: str = Field(description="Die (erste) Nachricht des Nutzers im Chat.")


class ChatOutput(BaseModel):
    reply: str = Field(description="Die Antwort an den Nutzer im Chat, in normaler Konversationssprache.")


class AskLibrarianArgs(BaseModel):
    question: str = Field(description="Die Recherche-Frage an den Librarian, der im Vault danach sucht.")


class CreateDirectoryArgs(BaseModel):
    path: str = Field(description="Vault-Pfad des neu anzulegenden Ordners (inkl. evtl. fehlender Zwischenordner).")


class CreateFileArgs(BaseModel):
    path: str = Field(description="Vault-Pfad der neu anzulegenden .md-Datei (muss noch nicht existieren).")
    content: str = Field(description="Inhalt der neuen Datei (reiner Markdown-Text, ohne Frontmatter).")


class EditFileArgs(BaseModel):
    path: str = Field(description="Vault-Pfad der zu bearbeitenden, bestehenden .md-Datei.")
    content: str = Field(description="Der NEUE vollständige Inhalt der Datei (ersetzt den bisherigen Inhalt unterhalb des Frontmatters komplett).")


class MoveFileArgs(BaseModel):
    path: str = Field(description="Vault-Pfad der zu verschiebenden/umzubenennenden bestehenden Datei.")
    new_path: str = Field(description="Neuer Vault-Pfad der Datei (muss noch nicht existieren, muss auf .md enden).")


class StartBackgroundTaskArgs(BaseModel):
    description: str = Field(
        description="Vollständige, in sich verständliche Beschreibung der Aufgabe für den Task-Agenten "
                     "(der Task-Agent kennt den bisherigen Chatverlauf nicht, also relevanten Kontext mit hineinfassen)."
    )


class CheckTaskStatusArgs(BaseModel):
    task_id: str = Field(description="Die task_id, die start_background_task zurückgegeben hat.")
