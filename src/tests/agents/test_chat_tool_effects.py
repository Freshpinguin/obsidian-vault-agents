from pathlib import Path
import pytest

from src.agentic.agents.chat import ChatAgent, start_wiki_chat
from src.agentic.engine import jobs
from src.tests.fakes.fake_llm import FakeLLM, final, tool_calls


COVERED_TOOLS = {
    "create_directory",
    "create_file",
    "edit_file",
    "move_file",
    "delete_file",
    "load_files",
    "ask_librarian",
    "web_search",
    "deep_reasoning",
    "start_background_task",
    "check_task_status",
}


def test_coverage_all_chat_tools_covered():
    actual_tools = {t.name for t in ChatAgent.tools}
    assert COVERED_TOOLS == actual_tools, (
        f"Differenz: {COVERED_TOOLS.symmetric_difference(actual_tools)}"
    )


def test_tool_effect_create_file_success(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("create_file", {"path": "Kulturen/Zeta.md", "content": "abc"})),
        final({"reply": "Datei Kulturen/Zeta.md wurde erstellt."}),
    )

    session = start_wiki_chat("Erstelle Datei Kulturen/Zeta.md")
    assert session.is_successful
    target = vault / "Kulturen" / "Zeta.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "abc\n"
    call2 = fake_llm.last_call("Chat")
    assert "Datei 'Kulturen/Zeta.md' wurde erstellt." in call2.tool_results[0]


def test_tool_effect_create_file_already_exists(vault: Path, fake_llm: FakeLLM):
    target = vault / "Grundannahmen.md"
    orig_content = target.read_text(encoding="utf-8")

    fake_llm.script(
        "Chat",
        tool_calls(("create_file", {"path": "Grundannahmen.md", "content": "Doppelt"})),
        final({"reply": "Konnte nicht erstellt werden, existiert schon."}),
    )

    session = start_wiki_chat("Erstelle Grundannahmen.md")
    assert session.is_successful
    assert target.read_text(encoding="utf-8") == orig_content
    call2 = fake_llm.last_call("Chat")
    assert "existiert bereits" in call2.tool_results[0]


def test_tool_effect_create_file_with_new_folder(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("create_file", {"path": "Neu/Unter/X.md", "content": "Inhalt X"})),
        final({"reply": "Datei im neuen Ordner erstellt."}),
    )

    session = start_wiki_chat("Erstelle Neu/Unter/X.md")
    assert session.is_successful
    target = vault / "Neu" / "Unter" / "X.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Inhalt X\n"


def test_tool_effect_create_directory_success(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("create_directory", {"path": "Neu/Ordner"})),
        final({"reply": "Ordner erstellt."}),
    )
    session = start_wiki_chat("Erstelle Ordner Neu/Ordner")
    assert session.is_successful
    assert (vault / "Neu" / "Ordner").is_dir()
    call2 = fake_llm.last_call("Chat")
    assert "Ordner 'Neu/Ordner' wurde erstellt." in call2.tool_results[0]


def test_tool_effect_create_directory_already_exists(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("create_directory", {"path": "Kulturen"})),
        final({"reply": "Ordner existiert schon."}),
    )
    session = start_wiki_chat("Erstelle Ordner Kulturen erneut")
    assert session.is_successful
    call2 = fake_llm.last_call("Chat")
    assert "existiert bereits" in call2.tool_results[0]


def test_tool_effect_edit_file_success(vault: Path, fake_llm: FakeLLM):
    target = vault / "Technologie" / "Antriebe.md"
    orig_text = target.read_text(encoding="utf-8")
    assert "---" in orig_text

    fake_llm.script(
        "Chat",
        tool_calls(("edit_file", {"path": "Technologie/Antriebe.md", "content": "Neuer Antriebstext"})),
        final({"reply": "Antriebe aktualisiert."}),
    )
    session = start_wiki_chat("Bearbeite Antriebe.md")
    assert session.is_successful
    new_text = target.read_text(encoding="utf-8")
    assert "Neuer Antriebstext" in new_text
    assert new_text.startswith("---\n")  # Frontmatter preserved


def test_tool_effect_edit_file_failure_nonexistent(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("edit_file", {"path": "GibtEsNicht.md", "content": "Text"})),
        final({"reply": "Datei nicht gefunden."}),
    )
    session = start_wiki_chat("Bearbeite GibtEsNicht.md")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Keine Datei" in call.tool_results[0]


def test_tool_effect_move_file_success(vault: Path, fake_llm: FakeLLM):
    source = vault / "Kulturen" / "Beispielvolk.md"
    content = source.read_text(encoding="utf-8")
    dest = vault / "Kulturen" / "Verschoben.md"

    fake_llm.script(
        "Chat",
        tool_calls(("move_file", {"path": "Kulturen/Beispielvolk.md", "new_path": "Kulturen/Verschoben.md"})),
        final({"reply": "Datei verschoben."}),
    )
    session = start_wiki_chat("Verschiebe Beispielvolk.md")
    assert session.is_successful
    assert not source.exists()
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == content


def test_tool_effect_move_file_failure_dest_exists(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("move_file", {"path": "Kulturen/Beispielvolk.md", "new_path": "Grundannahmen.md"})),
        final({"reply": "Ziel existiert schon."}),
    )
    session = start_wiki_chat("Verschiebe auf Grundannahmen")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "existiert bereits" in call.tool_results[0]


def test_tool_effect_delete_file_success(vault: Path, fake_llm: FakeLLM):
    target = vault / "Kulturen" / "Beispielvolk.md"
    assert target.exists()

    fake_llm.script(
        "Chat",
        tool_calls(("delete_file", {"path": "Kulturen/Beispielvolk.md"})),
        final({"reply": "Datei gelöscht."}),
    )
    session = start_wiki_chat("Lösche Beispielvolk.md")
    assert session.is_successful
    assert not target.exists()


def test_tool_effect_delete_file_failure_nonexistent(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("delete_file", {"path": "GibtEsGarNicht.md"})),
        final({"reply": "War schon weg."}),
    )
    session = start_wiki_chat("Lösche NichtExistierend")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Keine Datei" in call.tool_results[0]


def test_tool_effect_load_files_leaves_vault_unchanged(vault: Path, fake_llm: FakeLLM):
    snapshot_before = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}

    fake_llm.script(
        "Chat",
        tool_calls(("load_files", {"paths": ["Grundannahmen.md"]})),
        final({"reply": "Ich habe die Grundannahmen gelesen."}),
    )
    session = start_wiki_chat("Lies Grundannahmen")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Grundannahmen" in call.tool_results[0]

    snapshot_after = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}
    assert snapshot_before == snapshot_after


def test_tool_effect_ask_librarian_success(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("ask_librarian", {"question": "Gibt es Hyperraum?"})),
        final({"reply": "Der Librarian sagt: Ja, Hyperraum existiert."}),
    )
    fake_llm.script(
        "Librarian",
        final({"answer": "Hyperraum existiert laut Physik-Notizen.", "sources": ["Grundannahmen.md"]}),
    )

    session = start_wiki_chat("Gibt es Hyperraum?")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Hyperraum existiert" in call.tool_results[0]
    assert "Quellen: Grundannahmen.md" in call.tool_results[0]
    assert "Volltext der zitierten Quellen" in call.tool_results[0]


def test_tool_effect_ask_librarian_failure(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("ask_librarian", {"question": "Unbekanntes Thema?"})),
        final({"reply": "Der Librarian konnte nichts finden."}),
    )
    fake_llm.script(
        "Librarian",
        RuntimeError("Librarian crash"),
    )
    session = start_wiki_chat("Frag Librarian nach Fehler")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Fehler: Der Librarian" in call.tool_results[0]


def test_tool_effect_web_search(vault: Path, fake_llm: FakeLLM, fake_genai):
    fake_genai.text = "Alcubierre-Metrik ist theoretische Lösung der Relativitätstheorie."
    fake_genai.sources = [("NASA", "https://nasa.gov/warp")]

    fake_llm.script(
        "Chat",
        tool_calls(("web_search", {"query": "Alcubierre Antrieb"})),
        final({"reply": "Laut Websuche ist der Alcubierre-Antrieb theoretisch denkbar."}),
    )

    session = start_wiki_chat("Recherchiere Alcubierre")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Alcubierre-Metrik" in call.tool_results[0]
    assert "https://nasa.gov/warp" in call.tool_results[0]


def test_tool_effect_deep_reasoning_includes_file_context(vault: Path, fake_llm: FakeLLM, fake_antigravity):
    fake_antigravity.reply = "Detaillierte Analyse zu gesellschaftlichen Folgen."

    fake_llm.script(
        "Chat",
        tool_calls(("deep_reasoning", {"task": "Analysiere Kulturen", "file_paths": ["Grundannahmen.md"]})),
        final({"reply": "Hier ist die Tiefenanalyse."}),
    )

    session = start_wiki_chat("Analysiere Kulturen mit Grundannahmen")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Detaillierte Analyse" in call.tool_results[0]

    assert len(fake_antigravity.prompts) == 1
    assert "Analysiere Kulturen" in fake_antigravity.prompts[0]
    assert "## Kontext aus dem Wiki" in fake_antigravity.prompts[0]
    assert "Grundannahmen.md" in fake_antigravity.prompts[0]


def test_tool_effect_start_background_task(vault: Path, fake_llm: FakeLLM, sync_threads):
    def update_plan_fn(kwargs):
        active_id = list(jobs._jobs.keys())[-1]
        return tool_calls(("update_plan", {"task_id": active_id, "steps": [{"step": "Schritt 1", "status": "done"}]}))

    fake_llm.script(
        "TaskAgent",
        update_plan_fn,
        final({"summary": "Hintergrundarbeit komplett fertig."}),
    )

    fake_llm.script(
        "Chat",
        tool_calls(("start_background_task", {"description": "Ganz große Lore-Recherche"})),
        final({"reply": "Hintergrund-Aufgabe gestartet."}),
    )

    session = start_wiki_chat("Starte Hintergrundaufgabe")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Hintergrund-Aufgabe gestartet (task_id:" in call.tool_results[0]
    assert len(jobs._jobs) == 1


def test_tool_effect_check_task_status_known_and_unknown(vault: Path, fake_llm: FakeLLM, sync_threads):
    # Pre-populate a job
    job = jobs.TaskJob(task_id="test_tid", description="Test job", status="done")
    jobs._jobs["test_tid"] = job

    fake_llm.script(
        "Chat",
        tool_calls(("check_task_status", {"task_id": "test_tid"})),
        final({"reply": "Status abgefragt."}),
    )
    session = start_wiki_chat("Prüfe Status von test_tid")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Status: done" in call.tool_results[0]

    # Check unknown ID
    fake_llm.script(
        "Chat",
        tool_calls(("check_task_status", {"task_id": "ghost_id"})),
        final({"reply": "ID existiert nicht."}),
    )
    session2 = start_wiki_chat("Prüfe ghost")
    assert session2.is_successful
    call_ghost = fake_llm.last_call("Chat")
    assert "Fehler: Keine Hintergrund-Aufgabe mit der ID 'ghost_id'" in call_ghost.tool_results[0]


def test_tool_effect_multiple_mutations_in_single_turn(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(
            ("create_directory", {"path": "MultiDir"}),
            ("create_file", {"path": "MultiDir/File.md", "content": "Multi content"}),
        ),
        final({"reply": "Ordner und Datei angelegt."}),
    )

    session = start_wiki_chat("Erstelle MultiDir und MultiDir/File.md")
    assert session.is_successful
    assert (vault / "MultiDir").is_dir()
    assert (vault / "MultiDir" / "File.md").is_file()
    assert (vault / "MultiDir" / "File.md").read_text(encoding="utf-8") == "Multi content\n"


def test_smalltalk_final_answer_without_tools(vault: Path, fake_llm: FakeLLM):
    snapshot_before = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}

    fake_llm.script("Chat", final({"reply": "Hallo! Wie kann ich dir heute helfen?"}))
    session = start_wiki_chat("Hallo!")
    assert session.is_successful
    assert len(fake_llm.calls_for("Chat")) == 1

    snapshot_after = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}
    assert snapshot_before == snapshot_after


def test_hallucinated_mutation_rejected_then_succeeds(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        final({"reply": "Ich habe die Datei Kulturen/Halluziniert.md angelegt!"}),
        tool_calls(("create_file", {"path": "Kulturen/Halluziniert.md", "content": "Jetzt wirklich"})),
        final({"reply": "Jetzt ist Kulturen/Halluziniert.md angelegt."}),
    )

    session = start_wiki_chat("Leg Kulturen/Halluziniert.md an")
    assert session.is_successful
    calls = fake_llm.calls_for("Chat")
    assert len(calls) == 3
    assert "Deine Antwort wurde abgelehnt" in calls[1].last_user_message
    assert (vault / "Kulturen" / "Halluziniert.md").exists()
    assert (vault / "Kulturen" / "Halluziniert.md").read_text(encoding="utf-8") == "Jetzt wirklich\n"
