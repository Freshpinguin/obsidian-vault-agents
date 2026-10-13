"""Neu angelegte Notizen müssen SOFORT in der .ai_map.json und in der Datei-Map der
.index.md stehen – sonst sind sie für die Agenten bis zum (um 30 Minuten verzögerten)
Summarizer-Lauf unsichtbar."""
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from src.core.map_maintenance import _check_ai_map
from src.core.obsidian_processor import (
    PENDING_SUMMARY_TEXT,
    move_map_entry,
    register_pending_directory,
    register_pending_file,
    remove_map_entry,
)
from src.main import app
from src.navigation.vault_mutation import (
    create_directory,
    create_file,
    delete_file,
    move_file,
)
from src.navigation.vault_navigation import format_ai_map, load_ai_map

client = TestClient(app)


def _ai_map(vault: Path) -> dict:
    return json.loads((vault / ".ai_map.json").read_text(encoding="utf-8"))


class _ScheduleSpy:
    """Ersetzt den SummaryScheduler: merkt sich nur, was eingeplant wurde."""

    def __init__(self):
        self.scheduled: list[Path] = []

    def schedule(self, filepath, force=False):
        self.scheduled.append(Path(filepath))


def test_register_pending_file_adds_file_and_parent_dirs(vault: Path):
    target = vault / "Kulturen" / "Beziehungen" / "Neuling.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Neuling\n", encoding="utf-8")

    assert register_pending_file(target, vault) is True

    ai_map = _ai_map(vault)
    assert ai_map["files"]["Kulturen/Beziehungen/Neuling.md"] == PENDING_SUMMARY_TEXT
    # Alle übergeordneten Ordner sind vorgemerkt
    assert "Kulturen/Beziehungen" in ai_map["directories"]
    assert "Kulturen" in ai_map["directories"]


def test_register_pending_file_keeps_existing_folder_summary(vault: Path):
    before = _ai_map(vault)["directories"]["Kulturen"]
    assert before != PENDING_SUMMARY_TEXT

    target = vault / "Kulturen" / "Zweitling.md"
    target.write_text("# Zweitling\n", encoding="utf-8")
    register_pending_file(target, vault)

    assert _ai_map(vault)["directories"]["Kulturen"] == before


def test_register_pending_file_shows_up_in_index_md(vault: Path):
    index_path = vault / "Kulturen" / ".index.md"
    assert "Drittling.md" not in index_path.read_text(encoding="utf-8")

    target = vault / "Kulturen" / "Drittling.md"
    target.write_text("# Drittling\n", encoding="utf-8")
    register_pending_file(target, vault)

    content = index_path.read_text(encoding="utf-8")
    assert "Drittling.md" in content
    assert PENDING_SUMMARY_TEXT in content


def test_register_pending_file_ignores_system_files(vault: Path):
    assert register_pending_file(vault / "Kulturen" / ".index.md", vault) is False
    assert ".index.md" not in _ai_map(vault)["files"]
    assert "Kulturen/.index.md" not in _ai_map(vault)["files"]


def test_register_pending_file_rejects_path_outside_vault(vault: Path, tmp_path: Path):
    outside = tmp_path / "Fremd.md"
    outside.write_text("# Fremd\n", encoding="utf-8")
    assert register_pending_file(outside, vault) is False


def test_agent_create_file_registers_in_ai_map(vault: Path):
    """Der Agenten-Pfad (vault_mutation.create_file)."""
    res = create_file("Technologie/Agentennotiz.md", "# Von der KI", vault_root=vault)
    assert "erstellt" in res

    ai_map = _ai_map(vault)
    assert ai_map["files"]["Technologie/Agentennotiz.md"] == PENDING_SUMMARY_TEXT
    assert "Agentennotiz.md" in (vault / "Technologie" / ".index.md").read_text(encoding="utf-8")


def test_route_create_file_registers_in_ai_map(vault: Path):
    """Der UI-Pfad (Icon im Explorer -> POST /files/create-file)."""
    response = client.post(
        "/files/create-file",
        json={"path": "Kulturen/UiNotiz.md", "content": "# Aus dem Frontend"},
    )
    assert response.status_code == 200, response.text

    ai_map = _ai_map(vault)
    assert ai_map["files"]["Kulturen/UiNotiz.md"] == PENDING_SUMMARY_TEXT
    assert "UiNotiz.md" in (vault / "Kulturen" / ".index.md").read_text(encoding="utf-8")


def test_maintenance_backfills_handmade_note(vault: Path):
    """Von Hand angelegte Notiz, während der Server nicht lief: Der Wartungslauf
    trägt sie nach und plant die Zusammenfassung ein."""
    handmade = vault / "Technologie" / "Handarbeit.md"
    handmade.write_text("# Von Hand\n", encoding="utf-8")
    assert "Technologie/Handarbeit.md" not in _ai_map(vault)["files"]

    spy = _ScheduleSpy()
    _check_ai_map(vault, vault / ".ai_map.json", spy)

    assert _ai_map(vault)["files"]["Technologie/Handarbeit.md"] == PENDING_SUMMARY_TEXT
    assert handmade in spy.scheduled


# --------------------------------------------------------------- Verschieben


def test_move_map_entry_carries_summary_and_drops_old_key(vault: Path):
    """Beim Verschieben bleibt die bisherige Zusammenfassung erhalten – der Inhalt
    hat sich nicht geändert, also wird nichts neu generiert."""
    before = _ai_map(vault)["files"]["Kulturen/Apiden.md"]
    assert before != PENDING_SUMMARY_TEXT

    source = vault / "Kulturen" / "Apiden.md"
    target = vault / "Technologie" / "Apiden.md"
    source.rename(target)
    assert move_map_entry(source, target, vault) is True

    files = _ai_map(vault)["files"]
    assert "Kulturen/Apiden.md" not in files
    assert files["Technologie/Apiden.md"] == before


def test_move_map_entry_refreshes_both_index_files(vault: Path):
    source = vault / "Kulturen" / "Apiden.md"
    target = vault / "Technologie" / "Apiden.md"
    source.rename(target)
    move_map_entry(source, target, vault)

    assert "Apiden.md" not in (vault / "Kulturen" / ".index.md").read_text(encoding="utf-8")
    assert "Apiden.md" in (vault / "Technologie" / ".index.md").read_text(encoding="utf-8")


def test_move_map_entry_without_old_entry_is_pending(vault: Path):
    source = vault / "Kulturen" / "Frischling.md"
    source.write_text("# Frischling\n", encoding="utf-8")
    target = vault / "Technologie" / "Frischling.md"
    source.rename(target)
    move_map_entry(source, target, vault)

    assert _ai_map(vault)["files"]["Technologie/Frischling.md"] == PENDING_SUMMARY_TEXT


def test_agent_move_file_updates_ai_map(vault: Path):
    before = _ai_map(vault)["files"]["Kulturen/Apiden.md"]
    res = move_file("Kulturen/Apiden.md", "Technologie/Apiden.md", vault_root=vault)
    assert "verschoben" in res

    files = _ai_map(vault)["files"]
    assert "Kulturen/Apiden.md" not in files
    assert files["Technologie/Apiden.md"] == before


def test_route_move_updates_ai_map(vault: Path):
    before = _ai_map(vault)["files"]["Kulturen/Apiden.md"]
    response = client.post(
        "/files/move",
        json={"path": "Kulturen/Apiden.md", "new_path": "Technologie/Apiden.md"},
    )
    assert response.status_code == 200, response.text

    files = _ai_map(vault)["files"]
    assert "Kulturen/Apiden.md" not in files
    assert files["Technologie/Apiden.md"] == before


# ------------------------------------------------------------------- Ordner


def test_agent_created_folder_is_visible_to_agents(vault: Path):
    """Ein Agent darf keinen Ordner anlegen, den er danach selbst nicht sieht."""
    res = create_directory("Technologie/Waffensysteme", vault_root=vault)
    assert "erstellt" in res
    assert (vault / "Technologie" / "Waffensysteme").is_dir()

    ai_map = load_ai_map(vault_root=vault)
    assert ai_map["directories"]["Technologie/Waffensysteme"] == PENDING_SUMMARY_TEXT
    assert "Technologie/Waffensysteme/" in format_ai_map(ai_map)


def test_register_pending_directory_keeps_existing_summary(vault: Path):
    before = _ai_map(vault)["directories"]["Kulturen"]
    assert register_pending_directory(vault / "Kulturen", vault) is False
    assert _ai_map(vault)["directories"]["Kulturen"] == before


def test_register_pending_directory_ignores_hidden_folders(vault: Path):
    hidden = vault / ".obsidian"
    hidden.mkdir(exist_ok=True)
    assert register_pending_directory(hidden, vault) is False
    assert ".obsidian" not in _ai_map(vault)["directories"]


def test_register_pending_directory_ignores_vault_root(vault: Path):
    assert register_pending_directory(vault, vault) is False


# ---------------------------------------------------------------- Löschen


def test_remove_map_entry_drops_file_and_refreshes_index(vault: Path):
    target = vault / "Kulturen" / "Apiden.md"
    assert "Kulturen/Apiden.md" in _ai_map(vault)["files"]

    target.unlink()
    assert remove_map_entry(target, vault) is True

    assert "Kulturen/Apiden.md" not in _ai_map(vault)["files"]
    assert "Apiden.md" not in (vault / "Kulturen" / ".index.md").read_text(encoding="utf-8")


def test_remove_map_entry_prunes_whole_subtree_for_folder(vault: Path):
    """Mit einem Ordner verschwindet sein gesamter Inhalt aus der Map."""
    folder = vault / "Kulturen"
    before = _ai_map(vault)
    assert "Kulturen" in before["directories"]
    assert any(k.startswith("Kulturen/") for k in before["files"])

    shutil.rmtree(folder)
    assert remove_map_entry(folder, vault) is True

    after = _ai_map(vault)
    assert "Kulturen" not in after["directories"]
    assert not [k for k in after["files"] if k.startswith("Kulturen/")]
    assert not [k for k in after["directories"] if k.startswith("Kulturen/")]
    # Andere Ordner bleiben unberührt
    assert "Technologie" in after["directories"]
    assert "Grundannahmen.md" in after["files"]


def test_remove_map_entry_unknown_path_is_noop(vault: Path):
    before = _ai_map(vault)
    assert remove_map_entry(vault / "Kulturen" / "GibtEsNicht.md", vault) is False
    assert _ai_map(vault) == before


def test_remove_map_entry_rejects_outside_vault(vault: Path, tmp_path: Path):
    assert remove_map_entry(tmp_path / "Fremd.md", vault) is False


def test_remove_map_entry_ignores_vault_root(vault: Path):
    before = _ai_map(vault)
    assert remove_map_entry(vault, vault) is False
    assert _ai_map(vault) == before


def test_agent_delete_file_updates_ai_map(vault: Path):
    res = delete_file("Kulturen/Apiden.md", vault_root=vault)
    assert "gelöscht" in res
    assert "Kulturen/Apiden.md" not in _ai_map(vault)["files"]


def test_route_delete_file_updates_ai_map(vault: Path):
    response = client.delete("/files/content?path=Kulturen/Apiden.md")
    assert response.status_code == 200, response.text
    assert "Kulturen/Apiden.md" not in _ai_map(vault)["files"]
