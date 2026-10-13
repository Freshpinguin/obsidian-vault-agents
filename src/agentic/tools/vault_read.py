# src/agentic/tools/vault_read.py
"""WikiTool-Instanzen für lesende Operationen im Vault."""
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
    description="Lädt für mehrere Ordner auf einmal deren ausführliche Zusammenfassung samt Datei- und Unterordnerliste.",
    parameters=PathsArgs,
    func=_adapt(load_directory_summaries),
)

file_summaries_tool = WikiTool(
    name="load_file_summaries",
    description="Lädt für mehrere Dateien auf einmal deren Kurz-Zusammenfassung.",
    parameters=PathsArgs,
    func=_adapt(load_file_summaries),
)

files_tool = WikiTool(
    name="load_files",
    description="Lädt für mehrere Dateien auf einmal den vollen Inhalt. Die einzige verlässliche Quelle für Details.",
    parameters=PathsArgs,
    func=_adapt(load_files),
)

__all__ = [
    "directory_summaries_tool",
    "file_summaries_tool",
    "files_tool",
]
