from pathlib import Path
import json
import pytest

from src.navigation.vault_navigation import (
    VaultPathError,
    _resolve,
    _resolve_any,
    _read_md,
    _strip_frontmatter,
    format_ai_map,
    load_ai_map,
    load_directory_summary,
    load_directory_summaries,
    load_file,
    load_files,
    load_file_summary,
    load_file_summaries,
)


def test_load_files_single_success(vault: Path):
    res = load_files(["Overview.md"], vault_root=vault)
    assert "Overview.md" in res
    assert "Die Menschheit" in res or "Overview" in res


def test_load_files_multiple_success(vault: Path):
    res = load_files(["Overview.md", "Architecture/Data-Pipeline.md"], vault_root=vault)
    assert "Overview.md" in res
    assert "Architecture/Data-Pipeline.md" in res


def test_load_files_nonexistent(vault: Path):
    res = load_files(["ImaginaryFile.md"], vault_root=vault)
    assert "Error" in res and "No file" in res


def test_load_files_ambiguous(vault: Path):
    res = load_files(["Decisions"], vault_root=vault)
    assert "Error" in res and "is ambiguous" in res
    assert "Meetings/Decisions.md" in res
    assert "Architecture/Decisions.md" in res


def test_load_file_summaries(vault: Path):
    res = load_file_summaries(["Overview.md"], vault_root=vault)
    assert "Overview.md" in res
    # Nonexistent
    res_none = load_file_summaries(["NotThere.md"], vault_root=vault)
    assert "Error" in res_none


def test_load_directory_summaries(vault: Path):
    res = load_directory_summaries(["Meetings"], vault_root=vault)
    assert "Meetings" in res
    # Nonexistent
    res_none = load_directory_summaries(["NoFolder"], vault_root=vault)
    assert "Error" in res_none


def test_load_and_format_ai_map(vault: Path):
    ai_map = load_ai_map(vault_root=vault)
    assert isinstance(ai_map, dict)
    formatted = format_ai_map(ai_map)
    assert "Meetings" in formatted or "Folder" in formatted

    # Test format with empty/custom map
    empty_formatted = format_ai_map({"directories": {}, "files": {}})
    assert "(none)" in empty_formatted


def test_load_ai_map_without_file(vault: Path):
    map_file = vault / ".ai_map.json"
    if map_file.exists():
        map_file.unlink()
    ai_map = load_ai_map(vault_root=vault)
    assert ai_map == {"directories": {}, "files": {}}


def test_resolve_umlaut_folding(vault: Path):
    # Test directory or file with umlaut
    # Create a test folder with Umlaut
    test_dir = vault / "Übersicht"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "Sensors.md").write_text("Sensors Text\n", encoding="utf-8")

    # "Uebersicht" should resolve to Übersicht
    resolved = _resolve("Uebersicht/Sensors.md", vault_root=vault, expect="file")
    assert resolved.name == "Sensors.md"
    assert resolved.parent.name == "Übersicht"


def test_resolve_typo_tolerance(vault: Path):
    # Typo: Overveiw instead of Overview
    resolved = _resolve("Overveiw.md", vault_root=vault, expect="file")
    assert resolved.name == "Overview.md"


def test_read_md_and_strip_frontmatter():
    text = "---\nsummary: Test Summary\n---\nBody line 1\nBody line 2\n"
    stripped = _strip_frontmatter(text)
    assert stripped.strip() == "Body line 1\nBody line 2"

    no_fm = "Simple body text without fm"
    assert _strip_frontmatter(no_fm) == no_fm


def test_resolve_any_prefers_file_over_dir(vault: Path):
    # Create nested dir and file with same name (not directly under root)
    p_dir = vault / "Nested" / "SameName"
    p_dir.mkdir(parents=True, exist_ok=True)
    p_file = vault / "Nested2" / "SameName.md"
    p_file.parent.mkdir(parents=True, exist_ok=True)
    p_file.write_text("Same name file\n", encoding="utf-8")

    res_file = _resolve_any("SameName", vault_root=vault, prefer="file")
    assert res_file == p_file

    res_dir = _resolve_any("SameName", vault_root=vault, prefer="dir")
    assert res_dir == p_dir
