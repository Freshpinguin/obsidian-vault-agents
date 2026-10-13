from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import src.routes
from src.tests.fakes.fake_llm import FakeLLM, final, raw, tool_calls


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(src.routes.router)
    return TestClient(app)


def test_route_create_session_and_file_mutation(vault: Path, fake_llm: FakeLLM, api_client: TestClient):
    fake_llm.script(
        "Chat",
        tool_calls(("create_file", {"path": "Kulturen/Zeta.md", "content": "Zeta Inhalt"})),
        final({"reply": "Datei Kulturen/Zeta.md erstellt."}),
    )

    resp = api_client.post(
        "/sessions",
        json={"message": "Erstelle ein File unter Kulturen namens Zeta mit Inhalt Zeta Inhalt"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reply"] == "Datei Kulturen/Zeta.md erstellt."
    assert "session_id" in data
    session_id = data["session_id"]
    assert len(data["mutations"]) == 1
    assert data["mutations"][0]["tool"] == "create_file"
    assert data["mutations"][0]["path"] == "Kulturen/Zeta.md"

    # File exists on disk
    target = vault / "Kulturen" / "Zeta.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Zeta Inhalt\n"


def test_route_follow_up_message_with_mutation(vault: Path, fake_llm: FakeLLM, api_client: TestClient):
    # First turn: simple smalltalk or file creation
    fake_llm.script(
        "Chat",
        tool_calls(("create_file", {"path": "Kulturen/Note.md", "content": "Original"})),
        final({"reply": "Erstellt"}),
    )
    resp1 = api_client.post("/sessions", json={"message": "Erstelle Kulturen/Note.md"})
    assert resp1.status_code == 201
    session_id = resp1.json()["session_id"]

    # Second turn: edit file
    fake_llm.script(
        "Chat",
        tool_calls(("edit_file", {"path": "Kulturen/Note.md", "content": "Aktualisiert"})),
        final({"reply": "Geändert"}),
    )
    resp2 = api_client.post(f"/sessions/{session_id}/messages", json={"message": "Bearbeite Note.md"})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["reply"] == "Geändert"
    # Mutations must only contain THIS turn's mutations!
    assert len(data2["mutations"]) == 1
    assert data2["mutations"][0]["tool"] == "edit_file"
    assert data2["mutations"][0]["path"] == "Kulturen/Note.md"
    assert "Aktualisiert" in (vault / "Kulturen" / "Note.md").read_text(encoding="utf-8")


def test_route_move_file_mutation(vault: Path, fake_llm: FakeLLM, api_client: TestClient):
    fake_llm.script(
        "Chat",
        tool_calls(("move_file", {"path": "Kulturen/Beispielvolk.md", "new_path": "Kulturen/Ziel.md"})),
        final({"reply": "Verschoben"}),
    )
    resp = api_client.post("/sessions", json={"message": "Verschiebe Beispielvolk"})
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["mutations"]) == 1
    assert data["mutations"][0]["tool"] == "move_file"
    # Storage maps path or new_path; path is source
    assert data["mutations"][0]["path"] == "Kulturen/Beispielvolk.md"
    assert not (vault / "Kulturen" / "Beispielvolk.md").exists()
    assert (vault / "Kulturen" / "Ziel.md").exists()


def test_route_llm_failure_returns_502(fake_llm: FakeLLM, api_client: TestClient):
    # ChatAgent max_retries is 3, so exactly 4 attempts (1 initial + 3 retries)
    fake_llm.script(
        "Chat",
        raw("err 1"),
        raw("err 2"),
        raw("err 3"),
        raw("err 4"),
    )
    resp = api_client.post("/sessions", json={"message": "Hallo"})
    assert resp.status_code == 502
    assert "Chat-Agent konnte keine Antwort erzeugen" in resp.json()["detail"]


def test_route_unknown_session_returns_404(api_client: TestClient):
    resp_msg = api_client.post("/sessions/nonexistent_id/messages", json={"message": "Hi"})
    assert resp_msg.status_code == 404

    resp_del = api_client.delete("/sessions/nonexistent_id")
    assert resp_del.status_code == 404


def test_route_delete_session(fake_llm: FakeLLM, api_client: TestClient):
    fake_llm.script("Chat", final({"reply": "Hi"}))
    resp = api_client.post("/sessions", json={"message": "Hi"})
    session_id = resp.json()["session_id"]

    del_resp = api_client.delete(f"/sessions/{session_id}")
    assert del_resp.status_code == 204

    # Now trying to access it should be 404
    resp_after = api_client.post(f"/sessions/{session_id}/messages", json={"message": "Nochmal"})
    assert resp_after.status_code == 404


def test_route_active_file_header_in_llm_call(fake_llm: FakeLLM, api_client: TestClient):
    fake_llm.script("Chat", final({"reply": "Gesehen"}))
    resp = api_client.post(
        "/sessions",
        json={
            "message": "Füge Absatz hinzu",
            "active_file": "Grundannahmen.md",
            "active_file_summary": "Physik der Welt",
        },
    )
    assert resp.status_code == 201
    call = fake_llm.calls_for("Chat")[0]
    assert "[Im Editor geöffnete Notiz: Grundannahmen.md | ai_map Kurzzusammenfassung: Physik der Welt]" in call.last_user_message


def test_file_routes_endpoints(vault: Path, fake_llm: FakeLLM, api_client: TestClient):
    # 1. GET /files
    resp_tree = api_client.get("/files")
    assert resp_tree.status_code == 200
    data_tree = resp_tree.json()
    assert "items" in data_tree
    assert data_tree["total_files"] > 0

    # 2. GET /files/content
    resp_content = api_client.get("/files/content?path=Grundannahmen.md")
    assert resp_content.status_code == 200
    data_content = resp_content.json()
    assert data_content["name"] == "Grundannahmen.md"
    assert "raw_content" in data_content

    # 3. GET /files/{path}
    resp_path = api_client.get("/files/Grundannahmen.md")
    assert resp_path.status_code == 200

    # 4. Path traversal / not found
    resp_404 = api_client.get("/files/NichtVorhanden.md")
    assert resp_404.status_code == 404

    # 5. POST /files/summary
    fake_llm.script(
        "Summarizer",
        final({"document_summary": "Neue Zusammenfassung", "filemap_summary": "Kurz"}),
    )
    fake_llm.script(
        "FolderSummarizer",
        final({"folder_summary": "Ordner Neu", "dirmap_summary": "Ordner Kurz"}),
    )
    resp_summary = api_client.post("/files/summary", json={"path": "Grundannahmen.md"})
    assert resp_summary.status_code == 200
    assert resp_summary.json()["success"] is True


def test_route_create_session_stream(vault: Path, fake_llm: FakeLLM, api_client: TestClient):
    import json
    fake_llm.script(
        "Chat",
        tool_calls(("create_file", {"path": "Kulturen/Stream.md", "content": "Stream Inhalt"})),
        final({"reply": "Datei Kulturen/Stream.md erstellt."}),
    )

    resp = api_client.post(
        "/sessions",
        json={"message": "Erstelle Kulturen/Stream.md"},
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 201
    assert "text/event-stream" in resp.headers["content-type"]

    events = []
    for line in resp.text.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    status_events = [e for e in events if e.get("type") == "status"]
    done_events = [e for e in events if e.get("type") == "done"]

    assert len(status_events) >= 1
    assert any("Erstellt Datei" in e["message"] for e in status_events)
    assert len(done_events) == 1
    assert done_events[0]["reply"] == "Datei Kulturen/Stream.md erstellt."
    assert len(done_events[0]["mutations"]) == 1
    assert done_events[0]["mutations"][0]["tool"] == "create_file"


def test_route_message_stream(vault: Path, fake_llm: FakeLLM, api_client: TestClient):
    import json
    fake_llm.script(
        "Chat",
        final({"reply": "Hallo!"}),
    )

    resp1 = api_client.post("/sessions", json={"message": "Hi"})
    assert resp1.status_code == 201
    session_id = resp1.json()["session_id"]

    fake_llm.script(
        "Chat",
        tool_calls(("edit_file", {"path": "Grundannahmen.md", "content": "Neu"})),
        final({"reply": "Geändert"}),
    )

    resp2 = api_client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Ändere Grundannahmen"},
        headers={"Accept": "text/event-stream"},
    )
    assert resp2.status_code == 200
    assert "text/event-stream" in resp2.headers["content-type"]

    events = []
    for line in resp2.text.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    status_events = [e for e in events if e.get("type") == "status"]
    done_events = [e for e in events if e.get("type") == "done"]

    assert len(status_events) >= 1
    assert any("Bearbeitet Datei" in e["message"] for e in status_events)
    assert len(done_events) == 1
    assert done_events[0]["reply"] == "Geändert"
    assert len(done_events[0]["mutations"]) == 1
    assert done_events[0]["mutations"][0]["tool"] == "edit_file"
