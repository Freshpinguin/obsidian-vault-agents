# src/agentic/tools/vault_write.py
"""WikiTool-Instanzen für schreibende Operationen im Vault."""
from src.schemas.chat_schema import (
    CreateDirectoryArgs,
    CreateFileArgs,
    EditFileArgs,
    MoveFileArgs,
    DeleteFileArgs,
)
from src.schemas.tool_schema import WikiTool
from src.navigation import (
    create_directory,
    create_file,
    edit_file,
    move_file,
    delete_file,
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

__all__ = [
    "create_directory_tool",
    "create_file_tool",
    "move_file_tool",
    "edit_file_tool",
    "delete_file_tool",
]
