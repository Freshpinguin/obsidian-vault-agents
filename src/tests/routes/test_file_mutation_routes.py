# src/tests/routes/test_file_mutation_routes.py
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from src.main import app

client = TestClient(app)


def test_put_file_content_and_delete(tmp_path: Path, monkeypatch):
    from src.navigation import vault_navigation
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / ".ai_map.json").write_text('{"directories": {}, "files": {}}', encoding="utf-8")
    
    test_note = vault_dir / "TestNote.md"
    test_note.write_text("---\ntags:\n  - test\nai_summary: A test summary\n---\n# Original content\n", encoding="utf-8")

    monkeypatch.setattr(vault_navigation, "VAULT_ROOT", vault_dir)

    # 1. Update the file (change the body)
    response = client.put(
        "/files/content",
        json={"path": "TestNote.md", "content": "# Neuer Inhalt\nHier wurde etwas per Hand reingeschrieben."}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert "Neuer Inhalt" in data["file"]["body"]
    assert data["file"]["ai_summary"] == "A test summary"
    assert "test" in data["file"]["tags"]

    # 2. Update the file with its own frontmatter
    custom_content = "---\ntags:\n  - updated\n---\n# Eigener Body\n"
    response2 = client.put(
        "/files/content",
        json={"path": "TestNote.md", "content": custom_content}
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert "updated" in data2["file"]["tags"]
    # ai_summary is preserved, since the user did not explicitly overwrite it
    assert data2["file"]["ai_summary"] == "A test summary"

    # 3. Systemdatei ablehnen
    sys_response = client.put(
        "/files/content",
        json={"path": ".ai_map.json", "content": "{}"}
    )
    assert sys_response.status_code in (400, 404)

    # 4. Delete the file
    del_response = client.delete("/files/content?path=TestNote.md")
    assert del_response.status_code == 200, del_response.text
    del_data = del_response.json()
    assert del_data["success"] is True
    assert not test_note.exists()

    # 5. Deleting again yields a 404
    del_response404 = client.delete("/files/content?path=TestNote.md")
    assert del_response404.status_code == 404


def test_create_file_move_and_validation(tmp_path: Path, monkeypatch):
    """Creating folders over HTTP no longer exists (only agents create folders), so the
    destination folder is created directly on disk here."""
    from src.navigation import vault_navigation
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / ".ai_map.json").write_text('{"directories": {}, "files": {}}', encoding="utf-8")
    (vault_dir / "Projects" / "KI").mkdir(parents=True)

    monkeypatch.setattr(vault_navigation, "VAULT_ROOT", vault_dir)

    # 1. Create a note in the folder
    file_res = client.post(
        "/files/create-file",
        json={"path": "Projects/KI/Note1.md", "content": "# Notiz 1\nInhalt"},
    )
    assert file_res.status_code == 200, file_res.text
    assert file_res.json()["success"] is True
    created_file = vault_dir / "Projects" / "KI" / "Note1.md"
    assert created_file.is_file()
    assert "# Notiz 1" in created_file.read_text(encoding="utf-8")

    # 2. Move it: old path gone, new one present
    move_res = client.post(
        "/files/move",
        json={"path": "Projects/KI/Note1.md", "new_path": "Projects/Moved.md"},
    )
    assert move_res.status_code == 200, move_res.text
    assert move_res.json()["success"] is True
    assert not created_file.exists()
    assert (vault_dir / "Projects" / "Moved.md").is_file()

    # 3. An already existing path -> 409
    dup_file_res = client.post(
        "/files/create-file",
        json={"path": "Projects/Moved.md", "content": "# Duplikat"},
    )
    assert dup_file_res.status_code == 409

    # 4. The folder route has been removed
    gone = client.post("/files/create-folder", json={"path": "Projects/Neu"})
    assert gone.status_code in (404, 405)

    # 5. Path traversal is rejected; nothing is created outside the vault
    outside_file = tmp_path / "escape.md"
    traversal_res = client.post(
        "/files/create-file",
        json={"path": "../escape.md", "content": "# Escape"},
    )
    assert traversal_res.status_code in (400, 404)
    assert not outside_file.exists()

    # 6. Creating without a .md suffix always produces a .md file
    no_ext_res = client.post(
        "/files/create-file",
        json={"path": "Projects/KI/NoteWithoutExt", "content": "# Ohne Endung"},
    )
    assert no_ext_res.status_code == 200, no_ext_res.text
    assert no_ext_res.json()["path"] == "Projects/KI/NoteWithoutExt.md"
    assert (vault_dir / "Projects" / "KI" / "NoteWithoutExt.md").is_file()

    traversal_move_res = client.post(
        "/files/move",
        json={"path": "Projects/Moved.md", "new_path": "../escape.md"},
    )
    assert traversal_move_res.status_code in (400, 404)
    assert not outside_file.exists()
