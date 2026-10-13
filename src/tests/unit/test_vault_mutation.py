import unicodedata
from pathlib import Path
import pytest

from src.navigation.vault_mutation import (
    create_directory,
    create_file,
    delete_file,
    edit_file,
    move_file,
    _resolve_new_path,
)
from src.navigation.vault_navigation import VaultPathError


def test_create_file_success(vault: Path):
    res = create_file("Meetings/Zeta.md", "Zeta content", vault_root=vault)
    assert "was created" in res
    target = vault / "Meetings" / "Zeta.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Zeta content\n"


def test_create_file_creates_intermediate_dirs(vault: Path):
    res = create_file("Deep/Nested/Folder/Note.md", "Nested note", vault_root=vault)
    assert "was created" in res
    target = vault / "Deep" / "Nested" / "Folder" / "Note.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Nested note\n"


def test_create_file_already_exists_error(vault: Path):
    target = vault / "Overview.md"
    orig_content = target.read_text(encoding="utf-8")
    res = create_file("Overview.md", "New content", vault_root=vault)
    assert "Error" in res and "already exists" in res
    assert target.read_text(encoding="utf-8") == orig_content


def test_create_file_non_md_extension(vault: Path):
    res = create_file("Meetings/Zeta.txt", "Text file", vault_root=vault)
    assert "Error" in res and "only .md files" in res
    assert not (vault / "Meetings" / "Zeta.txt").exists()


def test_create_file_path_traversal_outside_vault(vault: Path):
    res = create_file("../outside.md", "Outside", vault_root=vault)
    assert "Error" in res and "outside the vault" in res

    res2 = create_file("Deep/../../../../outside.md", "Outside2", vault_root=vault)
    assert "Error" in res2 and "outside the vault" in res2


def test_create_file_strips_root_aliases(vault: Path):
    res = create_file("data/Meetings/AliasTest.md", "Content", vault_root=vault)
    assert "was created" in res
    assert (vault / "Meetings" / "AliasTest.md").exists()

    res2 = create_file("vault/Architecture/AliasTest2.md", "Content 2", vault_root=vault)
    assert "was created" in res2
    assert (vault / "Architecture" / "AliasTest2.md").exists()


def test_create_file_strips_frontmatter_from_content(vault: Path):
    content_with_fm = "---\ntitle: Vorlage\ntags: [test]\n---\nEchter Text"
    res = create_file("Meetings/NoFm.md", content_with_fm, vault_root=vault)
    assert "was created" in res
    target = vault / "Meetings" / "NoFm.md"
    saved = target.read_text(encoding="utf-8")
    assert "---\ntitle" not in saved
    assert saved.strip() == "Echter Text"


def test_create_file_unicode_nfc_nfd(vault: Path):
    # Ära as NFD (A + combining diaeresis)
    nfd_name = unicodedata.normalize("NFD", "Ära.md")
    res = create_file(f"Meetings/{nfd_name}", "Inhalt Ära", vault_root=vault)
    assert "was created" in res
    nfc_path = vault / "Meetings" / "Ära.md"
    assert nfc_path.exists()


def test_create_file_system_file_error(vault: Path):
    res1 = create_file(".index.md", "Index text", vault_root=vault)
    assert "Error" in res1 and "not a valid file name" in res1

    res2 = create_file("Meetings/.ai_map.json.md", "Test", vault_root=vault)
    # .ai_map is non summarizable
    assert "Error" in res2


def test_create_directory_success(vault: Path):
    res = create_directory("NewArea/Subfolder", vault_root=vault)
    assert "was created" in res
    assert (vault / "NewArea" / "Subfolder").is_dir()


def test_create_directory_already_exists(vault: Path):
    res = create_directory("Meetings", vault_root=vault)
    assert "Error" in res and "already exists (folder)" in res

    # File exists as directory target
    res2 = create_directory("Overview.md", vault_root=vault)
    assert "Error" in res2 and "already exists (file)" in res2


def test_create_directory_empty_path(vault: Path):
    res = create_directory("", vault_root=vault)
    assert "Error" in res and "No path was provided" in res


def test_edit_file_preserves_frontmatter(vault: Path):
    target = vault / "Overview.md"
    # Ensure it has frontmatter
    orig_text = target.read_text(encoding="utf-8")
    assert "---" in orig_text

    res = edit_file("Overview.md", "Komplett neuer Body", vault_root=vault)
    assert "was updated" in res
    new_text = target.read_text(encoding="utf-8")
    assert "Komplett neuer Body" in new_text
    assert new_text.startswith("---\n")
    # Frontmatter should not be duplicated
    assert new_text.count("---") == 2


def test_edit_file_strips_input_frontmatter(vault: Path):
    target = vault / "Overview.md"
    res = edit_file("Overview.md", "---\nalt: fm\n---\nNur Text", vault_root=vault)
    assert "was updated" in res
    new_text = target.read_text(encoding="utf-8")
    assert "Nur Text" in new_text
    assert "alt: fm" not in new_text


def test_edit_file_fuzzy_path(vault: Path):
    res = edit_file("architecture/data-pipeline", "New pipeline text", vault_root=vault)
    assert "was updated" in res
    target = vault / "Architecture" / "Data-Pipeline.md"
    assert "New pipeline text" in target.read_text(encoding="utf-8")


def test_edit_file_nonexistent(vault: Path):
    res = edit_file("NotPresent.md", "Inhalt", vault_root=vault)
    assert "Error" in res and "No file" in res


def test_edit_file_ambiguous_candidate_error(vault: Path):
    # Decisions exists in Meetings/Decisions.md and Architecture/Decisions.md
    res = edit_file("Decisions", "Text", vault_root=vault)
    assert "Error" in res and "is ambiguous" in res
    assert "Meetings/Decisions.md" in res
    assert "Architecture/Decisions.md" in res
    assert "Meetings/Decisions.md" in res
    assert "Architecture/Decisions.md" in res


def test_edit_file_system_file_error(vault: Path):
    res = edit_file(".index.md", "Inhalt", vault_root=vault)
    assert "Error" in res and "system file" in res


def test_move_file_success(vault: Path):
    source = vault / "Meetings" / "Weekly-Sync.md"
    content = source.read_text(encoding="utf-8")
    res = move_file("Meetings/Weekly-Sync.md", "Meetings/Moved.md", vault_root=vault)
    assert "moved" in res
    assert not source.exists()
    dest = vault / "Meetings" / "Moved.md"
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == content


def test_move_file_dest_already_exists_error(vault: Path):
    res = move_file("Meetings/Weekly-Sync.md", "Overview.md", vault_root=vault)
    assert "Error" in res and "already exists" in res
    assert (vault / "Meetings" / "Weekly-Sync.md").exists()


def test_move_file_dest_not_md(vault: Path):
    res = move_file("Meetings/Weekly-Sync.md", "Meetings/Beispiel.txt", vault_root=vault)
    assert "Error" in res and "destination must end in .md" in res
    assert (vault / "Meetings" / "Weekly-Sync.md").exists()


def test_move_file_dest_outside_vault(vault: Path):
    res = move_file("Meetings/Weekly-Sync.md", "../outside.md", vault_root=vault)
    assert "Error" in res and "outside the vault" in res


def test_move_file_creates_dest_parent_dir(vault: Path):
    res = move_file("Meetings/Weekly-Sync.md", "NewFolder/Sub/Example.md", vault_root=vault)
    assert "moved" in res
    assert (vault / "NewFolder" / "Sub" / "Example.md").exists()


def test_move_file_system_file_error(vault: Path):
    res = move_file(".index.md", "Normal.md", vault_root=vault)
    assert "Error" in res and "system file" in res


def test_delete_file_success(vault: Path):
    target = vault / "Meetings" / "Weekly-Sync.md"
    assert target.exists()
    res = delete_file("Meetings/Weekly-Sync.md", vault_root=vault)
    assert "was deleted" in res
    assert not target.exists()


def test_delete_file_nonexistent(vault: Path):
    res = delete_file("Unknown.md", vault_root=vault)
    assert "Error" in res and "No file" in res


def test_delete_file_system_file_error(vault: Path):
    res = delete_file(".index.md", vault_root=vault)
    assert "Error" in res and "system file" in res
