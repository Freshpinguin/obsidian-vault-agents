"""Newly created notes must appear in .ai_map.json and in the .index.md file map
IMMEDIATELY - otherwise they are invisible to the agents until the (30-minute-delayed)
summarizer run."""
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
    target = vault / "Meetings" / "Reviews" / "FreshNote.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# FreshNote\n", encoding="utf-8")

    assert register_pending_file(target, vault) is True

    ai_map = _ai_map(vault)
    assert ai_map["files"]["Meetings/Reviews/FreshNote.md"] == PENDING_SUMMARY_TEXT
    # All parent folders are registered
    assert "Meetings/Reviews" in ai_map["directories"]
    assert "Meetings" in ai_map["directories"]


def test_register_pending_file_keeps_existing_folder_summary(vault: Path):
    before = _ai_map(vault)["directories"]["Meetings"]
    assert before != PENDING_SUMMARY_TEXT

    target = vault / "Meetings" / "Second.md"
    target.write_text("# Second\n", encoding="utf-8")
    register_pending_file(target, vault)

    assert _ai_map(vault)["directories"]["Meetings"] == before


def test_register_pending_file_shows_up_in_index_md(vault: Path):
    index_path = vault / "Meetings" / ".index.md"
    assert "Third.md" not in index_path.read_text(encoding="utf-8")

    target = vault / "Meetings" / "Third.md"
    target.write_text("# Third\n", encoding="utf-8")
    register_pending_file(target, vault)

    content = index_path.read_text(encoding="utf-8")
    assert "Third.md" in content
    assert PENDING_SUMMARY_TEXT in content


def test_register_pending_file_ignores_system_files(vault: Path):
    assert register_pending_file(vault / "Meetings" / ".index.md", vault) is False
    assert ".index.md" not in _ai_map(vault)["files"]
    assert "Meetings/.index.md" not in _ai_map(vault)["files"]


def test_register_pending_file_rejects_path_outside_vault(vault: Path, tmp_path: Path):
    outside = tmp_path / "Foreign.md"
    outside.write_text("# Foreign\n", encoding="utf-8")
    assert register_pending_file(outside, vault) is False


def test_agent_create_file_registers_in_ai_map(vault: Path):
    """The agent path (vault_mutation.create_file)."""
    res = create_file("Architecture/AgentNote.md", "# From the AI", vault_root=vault)
    assert "was created" in res

    ai_map = _ai_map(vault)
    assert ai_map["files"]["Architecture/AgentNote.md"] == PENDING_SUMMARY_TEXT
    assert "AgentNote.md" in (vault / "Architecture" / ".index.md").read_text(encoding="utf-8")


def test_route_create_file_registers_in_ai_map(vault: Path):
    """The UI path (explorer icon -> POST /files/create-file)."""
    response = client.post(
        "/files/create-file",
        json={"path": "Meetings/UiNote.md", "content": "# From the frontend"},
    )
    assert response.status_code == 200, response.text

    ai_map = _ai_map(vault)
    assert ai_map["files"]["Meetings/UiNote.md"] == PENDING_SUMMARY_TEXT
    assert "UiNote.md" in (vault / "Meetings" / ".index.md").read_text(encoding="utf-8")


def test_maintenance_backfills_handmade_note(vault: Path):
    """A note created by hand while the server was not running: the maintenance pass
    backfills it and schedules the summary."""
    handmade = vault / "Architecture" / "Handmade.md"
    handmade.write_text("# By hand\n", encoding="utf-8")
    assert "Architecture/Handmade.md" not in _ai_map(vault)["files"]

    spy = _ScheduleSpy()
    _check_ai_map(vault, vault / ".ai_map.json", spy)

    assert _ai_map(vault)["files"]["Architecture/Handmade.md"] == PENDING_SUMMARY_TEXT
    assert handmade in spy.scheduled


# ------------------------------------------------------------------- Moving


def test_move_map_entry_carries_summary_and_drops_old_key(vault: Path):
    """On a move the existing summary is preserved - the content has not changed, so
    nothing is regenerated."""
    before = _ai_map(vault)["files"]["Meetings/Kickoff.md"]
    assert before != PENDING_SUMMARY_TEXT

    source = vault / "Meetings" / "Kickoff.md"
    target = vault / "Architecture" / "Kickoff.md"
    source.rename(target)
    assert move_map_entry(source, target, vault) is True

    files = _ai_map(vault)["files"]
    assert "Meetings/Kickoff.md" not in files
    assert files["Architecture/Kickoff.md"] == before


def test_move_map_entry_refreshes_both_index_files(vault: Path):
    source = vault / "Meetings" / "Kickoff.md"
    target = vault / "Architecture" / "Kickoff.md"
    source.rename(target)
    move_map_entry(source, target, vault)

    assert "Kickoff.md" not in (vault / "Meetings" / ".index.md").read_text(encoding="utf-8")
    assert "Kickoff.md" in (vault / "Architecture" / ".index.md").read_text(encoding="utf-8")


def test_move_map_entry_without_old_entry_is_pending(vault: Path):
    source = vault / "Meetings" / "FreshFile.md"
    source.write_text("# FreshFile\n", encoding="utf-8")
    target = vault / "Architecture" / "FreshFile.md"
    source.rename(target)
    move_map_entry(source, target, vault)

    assert _ai_map(vault)["files"]["Architecture/FreshFile.md"] == PENDING_SUMMARY_TEXT


def test_agent_move_file_updates_ai_map(vault: Path):
    before = _ai_map(vault)["files"]["Meetings/Kickoff.md"]
    res = move_file("Meetings/Kickoff.md", "Architecture/Kickoff.md", vault_root=vault)
    assert "moved" in res

    files = _ai_map(vault)["files"]
    assert "Meetings/Kickoff.md" not in files
    assert files["Architecture/Kickoff.md"] == before


def test_route_move_updates_ai_map(vault: Path):
    before = _ai_map(vault)["files"]["Meetings/Kickoff.md"]
    response = client.post(
        "/files/move",
        json={"path": "Meetings/Kickoff.md", "new_path": "Architecture/Kickoff.md"},
    )
    assert response.status_code == 200, response.text

    files = _ai_map(vault)["files"]
    assert "Meetings/Kickoff.md" not in files
    assert files["Architecture/Kickoff.md"] == before


# ------------------------------------------------------------------ Folders


def test_agent_created_folder_is_visible_to_agents(vault: Path):
    """An agent must not create a folder it then cannot see itself."""
    res = create_directory("Architecture/Runtime", vault_root=vault)
    assert "was created" in res
    assert (vault / "Architecture" / "Runtime").is_dir()

    ai_map = load_ai_map(vault_root=vault)
    assert ai_map["directories"]["Architecture/Runtime"] == PENDING_SUMMARY_TEXT
    assert "Architecture/Runtime/" in format_ai_map(ai_map)


def test_register_pending_directory_keeps_existing_summary(vault: Path):
    before = _ai_map(vault)["directories"]["Meetings"]
    assert register_pending_directory(vault / "Meetings", vault) is False
    assert _ai_map(vault)["directories"]["Meetings"] == before


def test_register_pending_directory_ignores_hidden_folders(vault: Path):
    hidden = vault / ".obsidian"
    hidden.mkdir(exist_ok=True)
    assert register_pending_directory(hidden, vault) is False
    assert ".obsidian" not in _ai_map(vault)["directories"]


def test_register_pending_directory_ignores_vault_root(vault: Path):
    assert register_pending_directory(vault, vault) is False


# ----------------------------------------------------------------- Deleting


def test_remove_map_entry_drops_file_and_refreshes_index(vault: Path):
    target = vault / "Meetings" / "Kickoff.md"
    assert "Meetings/Kickoff.md" in _ai_map(vault)["files"]

    target.unlink()
    assert remove_map_entry(target, vault) is True

    assert "Meetings/Kickoff.md" not in _ai_map(vault)["files"]
    assert "Kickoff.md" not in (vault / "Meetings" / ".index.md").read_text(encoding="utf-8")


def test_remove_map_entry_prunes_whole_subtree_for_folder(vault: Path):
    """Deleting a folder removes all of its content from the map."""
    folder = vault / "Meetings"
    before = _ai_map(vault)
    assert "Meetings" in before["directories"]
    assert any(k.startswith("Meetings/") for k in before["files"])

    shutil.rmtree(folder)
    assert remove_map_entry(folder, vault) is True

    after = _ai_map(vault)
    assert "Meetings" not in after["directories"]
    assert not [k for k in after["files"] if k.startswith("Meetings/")]
    assert not [k for k in after["directories"] if k.startswith("Meetings/")]
    # Other folders remain untouched
    assert "Architecture" in after["directories"]
    assert "Overview.md" in after["files"]


def test_remove_map_entry_unknown_path_is_noop(vault: Path):
    before = _ai_map(vault)
    assert remove_map_entry(vault / "Meetings" / "DoesNotExist.md", vault) is False
    assert _ai_map(vault) == before


def test_remove_map_entry_rejects_outside_vault(vault: Path, tmp_path: Path):
    assert remove_map_entry(tmp_path / "Foreign.md", vault) is False


def test_remove_map_entry_ignores_vault_root(vault: Path):
    before = _ai_map(vault)
    assert remove_map_entry(vault, vault) is False
    assert _ai_map(vault) == before


def test_agent_delete_file_updates_ai_map(vault: Path):
    res = delete_file("Meetings/Kickoff.md", vault_root=vault)
    assert "was deleted" in res
    assert "Meetings/Kickoff.md" not in _ai_map(vault)["files"]


def test_route_delete_file_updates_ai_map(vault: Path):
    response = client.delete("/files/content?path=Meetings/Kickoff.md")
    assert response.status_code == 200, response.text
    assert "Meetings/Kickoff.md" not in _ai_map(vault)["files"]
