import json
from pathlib import Path
import pytest
import yaml

from src.core.obsidian_processor import (
    ObsidianVaultManager,
    process_obsidian_file,
    process_folder_summary,
)
from src.navigation.vault_navigation import load_ai_map
from src.tests.fakes.fake_llm import FakeLLM, final, raw


def test_summarizer_success_updates_frontmatter_and_ai_map_and_triggers_folder_summarizer(
    vault: Path, fake_llm: FakeLLM
):
    target_file = vault / "Meetings" / "Weekly-Sync.md"

    fake_llm.script(
        "Summarizer",
        final({
            "document_summary": "Eine detaillierte Zusammenfassung der Kultur des Weekly-Syncs.",
            "filemap_summary": "Kurzeintrag Weekly-Sync.",
        }),
    )
    fake_llm.script(
        "FolderSummarizer",
        final({
            "folder_summary": "The Meetings folder holds notes, decisions and planning.",
            "dirmap_summary": "Kurzeintrag Meetings Ordner.",
        }),
    )

    res = process_obsidian_file(vault, target_file)
    assert res is True

    # Check that Summarizer received current_content and prev_doc_summary
    call_sum = fake_llm.calls_for("Summarizer")[0]
    assert "current_content" in call_sum.last_user_message
    assert "prev_doc_summary" in call_sum.last_user_message

    # Verify file frontmatter updated
    content = target_file.read_text(encoding="utf-8")
    assert "summary: Eine detaillierte Zusammenfassung der Kultur des Weekly-Syncs." in content

    # Verify .ai_map.json updated
    ai_map = load_ai_map(vault)
    assert ai_map["files"]["Meetings/Weekly-Sync.md"] == "Kurzeintrag Weekly-Sync."
    assert ai_map["directories"]["Meetings"] == "Kurzeintrag Meetings Ordner."


def test_summarizer_failure_leaves_file_byte_identical(vault: Path, fake_llm: FakeLLM):
    target_file = vault / "Overview.md"
    bytes_before = target_file.read_bytes()

    # Repeat raw invalid response for max_retries + 1 (4 attempts)
    fake_llm.script(
        "Summarizer",
        raw("kaputt 1"),
        raw("kaputt 2"),
        raw("kaputt 3"),
        raw("kaputt 4"),
    )

    res = process_obsidian_file(vault, target_file)
    assert res is False
    assert target_file.read_bytes() == bytes_before


def test_folder_summarizer_writes_index_and_ai_map(vault: Path, fake_llm: FakeLLM):
    target_folder = vault / "Meetings"
    index_file = target_folder / ".index.md"

    fake_llm.script(
        "FolderSummarizer",
        final({
            "folder_summary": "Detailed summary of the Meetings folder.",
            "dirmap_summary": "Kurz Meetings.",
        }),
    )

    res = process_folder_summary(vault, target_folder)
    assert res is True
    assert index_file.exists()
    index_text = index_file.read_text(encoding="utf-8")
    assert "summary: Detailed summary of the Meetings folder." in index_text

    ai_map = load_ai_map(vault)
    assert ai_map["directories"]["Meetings"] == "Kurz Meetings."


def test_folder_summarizer_returns_false_when_summaries_unchanged(vault: Path, fake_llm: FakeLLM):
    target_folder = vault / "Meetings"

    # Run once to set the summaries
    fake_llm.script(
        "FolderSummarizer",
        final({
            "folder_summary": "Gleicher Text",
            "dirmap_summary": "Gleicher Kurzeintrag",
        }),
    )
    process_folder_summary(vault, target_folder)

    # Run again with identical output
    fake_llm.script(
        "FolderSummarizer",
        final({
            "folder_summary": "Gleicher Text",
            "dirmap_summary": "Gleicher Kurzeintrag",
        }),
    )
    res_second = process_folder_summary(vault, target_folder)
    # Since summary is identical, returns False (cascade stops)
    assert res_second is False


def test_folder_summarizer_error_leaves_index_file_unchanged(vault: Path, fake_llm: FakeLLM):
    target_folder = vault / "Meetings"
    index_file = target_folder / ".index.md"
    # Ensure index exists first
    index_file.write_text("---\nsummary: Original\n---\nBody", encoding="utf-8")
    orig_bytes = index_file.read_bytes()

    fake_llm.script(
        "FolderSummarizer",
        raw("err1"),
        raw("err2"),
        raw("err3"),
        raw("err4"),
    )

    res = process_folder_summary(vault, target_folder)
    assert res is False
    assert index_file.read_bytes() == orig_bytes
