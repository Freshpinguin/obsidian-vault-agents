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
    test_note.write_text("---\ntags:\n  - test\nai_summary: Eine Testzusammenfassung\n---\n# Ursprünglicher Inhalt\n", encoding="utf-8")

    monkeypatch.setattr(vault_navigation, "VAULT_ROOT", vault_dir)

    # 1. Datei aktualisieren (Body ändern)
    response = client.put(
        "/files/content",
        json={"path": "TestNote.md", "content": "# Neuer Inhalt\nHier wurde etwas per Hand reingeschrieben."}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert "Neuer Inhalt" in data["file"]["body"]
    assert data["file"]["ai_summary"] == "Eine Testzusammenfassung"
    assert "test" in data["file"]["tags"]

    # 2. Datei mit eigenem Frontmatter aktualisieren
    custom_content = "---\ntags:\n  - updated\n---\n# Eigener Body\n"
    response2 = client.put(
        "/files/content",
        json={"path": "TestNote.md", "content": custom_content}
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert "updated" in data2["file"]["tags"]
    # ai_summary bleibt erhalten, da vom Nutzer nicht explizit überschrieben
    assert data2["file"]["ai_summary"] == "Eine Testzusammenfassung"

    # 3. Systemdatei ablehnen
    sys_response = client.put(
        "/files/content",
        json={"path": ".ai_map.json", "content": "{}"}
    )
    assert sys_response.status_code in (400, 404)

    # 4. Datei löschen
    del_response = client.delete("/files/content?path=TestNote.md")
    assert del_response.status_code == 200, del_response.text
    del_data = del_response.json()
    assert del_data["success"] is True
    assert not test_note.exists()

    # 5. Erneutes Löschen führt zu 404
    del_response404 = client.delete("/files/content?path=TestNote.md")
    assert del_response404.status_code == 404


def test_create_file_move_and_validation(tmp_path: Path, monkeypatch):
    """Ordner-Anlage ueber HTTP gibt es nicht mehr (nur noch Agenten legen Ordner an),
    daher wird der Zielordner hier direkt auf der Platte erzeugt."""
    from src.navigation import vault_navigation
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / ".ai_map.json").write_text('{"directories": {}, "files": {}}', encoding="utf-8")
    (vault_dir / "Projekte" / "KI").mkdir(parents=True)

    monkeypatch.setattr(vault_navigation, "VAULT_ROOT", vault_dir)

    # 1. Notiz im Ordner anlegen
    file_res = client.post(
        "/files/create-file",
        json={"path": "Projekte/KI/Notiz1.md", "content": "# Notiz 1\nInhalt"},
    )
    assert file_res.status_code == 200, file_res.text
    assert file_res.json()["success"] is True
    created_file = vault_dir / "Projekte" / "KI" / "Notiz1.md"
    assert created_file.is_file()
    assert "# Notiz 1" in created_file.read_text(encoding="utf-8")

    # 2. Verschieben: alter Pfad weg, neuer da
    move_res = client.post(
        "/files/move",
        json={"path": "Projekte/KI/Notiz1.md", "new_path": "Projekte/Verschoben.md"},
    )
    assert move_res.status_code == 200, move_res.text
    assert move_res.json()["success"] is True
    assert not created_file.exists()
    assert (vault_dir / "Projekte" / "Verschoben.md").is_file()

    # 3. Bereits existierender Pfad -> 409
    dup_file_res = client.post(
        "/files/create-file",
        json={"path": "Projekte/Verschoben.md", "content": "# Duplikat"},
    )
    assert dup_file_res.status_code == 409

    # 4. Die Ordner-Route ist entfernt
    gone = client.post("/files/create-folder", json={"path": "Projekte/Neu"})
    assert gone.status_code in (404, 405)

    # 5. Pfad-Traversierung wird abgelehnt, nichts entsteht ausserhalb des Vaults
    outside_file = tmp_path / "escape.md"
    traversal_res = client.post(
        "/files/create-file",
        json={"path": "../escape.md", "content": "# Escape"},
    )
    assert traversal_res.status_code in (400, 404)
    assert not outside_file.exists()

    traversal_move_res = client.post(
        "/files/move",
        json={"path": "Projekte/Verschoben.md", "new_path": "../escape.md"},
    )
    assert traversal_move_res.status_code in (400, 404)
    assert not outside_file.exists()
