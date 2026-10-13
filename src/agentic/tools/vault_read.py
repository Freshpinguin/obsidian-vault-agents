# src/agentic/tools/vault_read.py
"""WikiTool instances for read operations on the vault."""
from src.schemas.tool_args import PathsArgs
from src.schemas.tool_schema import WikiTool
from src.navigation import (
    load_directory_summaries,
    load_file_summaries,
    load_files,
)


def _adapt(batch_loader):
    def call(paths: list[str]) -> str:
        return batch_loader(paths)
    return call


directory_summaries_tool = WikiTool(
    name="load_directory_summaries",
    description="Loads the detailed summary of several folders at once, including their file and subfolder listings.",
    parameters=PathsArgs,
    func=_adapt(load_directory_summaries),
)

file_summaries_tool = WikiTool(
    name="load_file_summaries",
    description="Loads the short summary of several files at once.",
    parameters=PathsArgs,
    func=_adapt(load_file_summaries),
)

files_tool = WikiTool(
    name="load_files",
    description="Loads the full content of several files at once. The only reliable source for details.",
    parameters=PathsArgs,
    func=_adapt(load_files),
)

__all__ = [
    "directory_summaries_tool",
    "file_summaries_tool",
    "files_tool",
]
