# src/agentic/tools/vault_write.py
"""WikiTool instances for write operations on the vault."""
from src.schemas.tool_args import (
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
    description="Creates a new (empty) folder in the vault, including any missing parent folders.",
    parameters=CreateDirectoryArgs,
    func=create_directory,
)

create_file_tool = WikiTool(
    name="create_file",
    description="Creates a new .md file with the given content in the vault (the path must not exist yet).",
    parameters=CreateFileArgs,
    func=create_file,
)

move_file_tool = WikiTool(
    name="move_file",
    description="Moves/renames an existing file in the vault (the destination path must not exist yet).",
    parameters=MoveFileArgs,
    func=move_file,
)

edit_file_tool = WikiTool(
    name="edit_file",
    description="Replaces the content of an EXISTING .md file in the vault (frontmatter is preserved). Use this for changes to existing files - do NOT combine move_file+create_file.",
    parameters=EditFileArgs,
    func=edit_file,
)

delete_file_tool = WikiTool(
    name="delete_file",
    description="Permanently deletes an existing .md file from the vault.",
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
