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
