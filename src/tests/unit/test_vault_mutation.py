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
    res = create_file("Kulturen/Zeta.md", "Zeta content", vault_root=vault)
    assert "erstellt" in res
    target = vault / "Kulturen" / "Zeta.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Zeta content\n"


def test_create_file_creates_intermediate_dirs(vault: Path):
    res = create_file("Deep/Nested/Folder/Note.md", "Nested note", vault_root=vault)
    assert "erstellt" in res
    target = vault / "Deep" / "Nested" / "Folder" / "Note.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Nested note\n"


def test_create_file_already_exists_error(vault: Path):
    target = vault / "Grundannahmen.md"
    orig_content = target.read_text(encoding="utf-8")
    res = create_file("Grundannahmen.md", "New content", vault_root=vault)
    assert "Fehler" in res and "existiert bereits" in res
    assert target.read_text(encoding="utf-8") == orig_content


def test_create_file_non_md_extension(vault: Path):
    res = create_file("Kulturen/Zeta.txt", "Text file", vault_root=vault)
    assert "Fehler" in res and "Nur .md-Dateien" in res
    assert not (vault / "Kulturen" / "Zeta.txt").exists()


def test_create_file_path_traversal_outside_vault(vault: Path):
    res = create_file("../outside.md", "Outside", vault_root=vault)
    assert "Fehler" in res and "außerhalb des Vaults" in res

    res2 = create_file("Deep/../../../../outside.md", "Outside2", vault_root=vault)
    assert "Fehler" in res2 and "außerhalb des Vaults" in res2


def test_create_file_strips_root_aliases(vault: Path):
    res = create_file("data/Kulturen/AliasTest.md", "Content", vault_root=vault)
    assert "erstellt" in res
    assert (vault / "Kulturen" / "AliasTest.md").exists()

    res2 = create_file("vault/Technologie/AliasTest2.md", "Content 2", vault_root=vault)
    assert "erstellt" in res2
    assert (vault / "Technologie" / "AliasTest2.md").exists()


def test_create_file_strips_frontmatter_from_content(vault: Path):
    content_with_fm = "---\ntitle: Vorlage\ntags: [test]\n---\nEchter Text"
    res = create_file("Kulturen/NoFm.md", content_with_fm, vault_root=vault)
    assert "erstellt" in res
    target = vault / "Kulturen" / "NoFm.md"
    saved = target.read_text(encoding="utf-8")
    assert "---\ntitle" not in saved
    assert saved.strip() == "Echter Text"


def test_create_file_unicode_nfc_nfd(vault: Path):
    # Ära as NFD (A + combining diaeresis)
    nfd_name = unicodedata.normalize("NFD", "Ära.md")
    res = create_file(f"Kulturen/{nfd_name}", "Inhalt Ära", vault_root=vault)
    assert "erstellt" in res
    nfc_path = vault / "Kulturen" / "Ära.md"
    assert nfc_path.exists()


def test_create_file_system_file_error(vault: Path):
    res1 = create_file(".index.md", "Index text", vault_root=vault)
    assert "Fehler" in res1 and "kein gültiger Dateiname" in res1

    res2 = create_file("Kulturen/.ai_map.json.md", "Test", vault_root=vault)
    # .ai_map is non summarizable
    assert "Fehler" in res2


def test_create_directory_success(vault: Path):
    res = create_directory("NeueWelt/Unterordner", vault_root=vault)
    assert "erstellt" in res
    assert (vault / "NeueWelt" / "Unterordner").is_dir()


def test_create_directory_already_exists(vault: Path):
    res = create_directory("Kulturen", vault_root=vault)
    assert "Fehler" in res and "existiert bereits (Ordner)" in res

    # File exists as directory target
    res2 = create_directory("Grundannahmen.md", vault_root=vault)
    assert "Fehler" in res2 and "existiert bereits (Datei)" in res2


def test_create_directory_empty_path(vault: Path):
    res = create_directory("", vault_root=vault)
    assert "Fehler" in res and "kein Pfad angegeben" in res


def test_edit_file_preserves_frontmatter(vault: Path):
    target = vault / "Grundannahmen.md"
    # Ensure it has frontmatter
    orig_text = target.read_text(encoding="utf-8")
    assert "---" in orig_text

    res = edit_file("Grundannahmen.md", "Komplett neuer Body", vault_root=vault)
    assert "aktualisiert" in res
    new_text = target.read_text(encoding="utf-8")
    assert "Komplett neuer Body" in new_text
    assert new_text.startswith("---\n")
    # Frontmatter should not be duplicated
    assert new_text.count("---") == 2


def test_edit_file_strips_input_frontmatter(vault: Path):
    target = vault / "Grundannahmen.md"
    res = edit_file("Grundannahmen.md", "---\nalt: fm\n---\nNur Text", vault_root=vault)
    assert "aktualisiert" in res
    new_text = target.read_text(encoding="utf-8")
    assert "Nur Text" in new_text
    assert "alt: fm" not in new_text


def test_edit_file_fuzzy_path(vault: Path):
    res = edit_file("technologie/antriebe", "Neuer Antriebstext", vault_root=vault)
    assert "aktualisiert" in res
    target = vault / "Technologie" / "Antriebe.md"
    assert "Neuer Antriebstext" in target.read_text(encoding="utf-8")


def test_edit_file_nonexistent(vault: Path):
    res = edit_file("NichtVorhanden.md", "Inhalt", vault_root=vault)
    assert "Fehler" in res and "Keine Datei" in res


def test_edit_file_ambiguous_candidate_error(vault: Path):
    # Gasgeborene exists in Kulturen/Gasgeborene.md and Technologie/Gasgeborene.md
    res = edit_file("Gasgeborene", "Text", vault_root=vault)
    assert "Fehler" in res and "nicht eindeutig" in res
    assert "Kulturen/Gasgeborene.md" in res
    assert "Technologie/Gasgeborene.md" in res
    assert "Kulturen/Gasgeborene.md" in res
    assert "Technologie/Gasgeborene.md" in res


def test_edit_file_system_file_error(vault: Path):
    res = edit_file(".index.md", "Inhalt", vault_root=vault)
    assert "Fehler" in res and "Systemdatei" in res


def test_move_file_success(vault: Path):
    source = vault / "Kulturen" / "Beispielvolk.md"
    content = source.read_text(encoding="utf-8")
    res = move_file("Kulturen/Beispielvolk.md", "Kulturen/Verschoben.md", vault_root=vault)
    assert "verschoben" in res
    assert not source.exists()
    dest = vault / "Kulturen" / "Verschoben.md"
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == content


def test_move_file_dest_already_exists_error(vault: Path):
    res = move_file("Kulturen/Beispielvolk.md", "Grundannahmen.md", vault_root=vault)
    assert "Fehler" in res and "existiert bereits" in res
    assert (vault / "Kulturen" / "Beispielvolk.md").exists()


def test_move_file_dest_not_md(vault: Path):
    res = move_file("Kulturen/Beispielvolk.md", "Kulturen/Beispiel.txt", vault_root=vault)
    assert "Fehler" in res and "Ziel muss auf .md enden" in res
    assert (vault / "Kulturen" / "Beispielvolk.md").exists()


def test_move_file_dest_outside_vault(vault: Path):
    res = move_file("Kulturen/Beispielvolk.md", "../outside.md", vault_root=vault)
    assert "Fehler" in res and "außerhalb des Vaults" in res


def test_move_file_creates_dest_parent_dir(vault: Path):
    res = move_file("Kulturen/Beispielvolk.md", "NeuerOrdner/Sub/Beispiel.md", vault_root=vault)
    assert "verschoben" in res
    assert (vault / "NeuerOrdner" / "Sub" / "Beispiel.md").exists()


def test_move_file_system_file_error(vault: Path):
    res = move_file(".index.md", "Normal.md", vault_root=vault)
    assert "Fehler" in res and "Systemdatei" in res


def test_delete_file_success(vault: Path):
    target = vault / "Kulturen" / "Beispielvolk.md"
    assert target.exists()
    res = delete_file("Kulturen/Beispielvolk.md", vault_root=vault)
    assert "gelöscht" in res
    assert not target.exists()


def test_delete_file_nonexistent(vault: Path):
    res = delete_file("Unbekannt.md", vault_root=vault)
    assert "Fehler" in res and "Keine Datei" in res


def test_delete_file_system_file_error(vault: Path):
    res = delete_file(".index.md", vault_root=vault)
    assert "Fehler" in res and "Systemdatei" in res
