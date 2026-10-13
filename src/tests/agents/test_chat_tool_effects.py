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
        tool_calls(("create_file", {"path": "Meetings/Zeta.md", "content": "abc"})),
        final({"reply": "File Meetings/Zeta.md was created."}),
    )

    session = start_wiki_chat("Create file Meetings/Zeta.md")
    assert session.is_successful
    target = vault / "Meetings" / "Zeta.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "abc\n"
    call2 = fake_llm.last_call("Chat")
    assert "File 'Meetings/Zeta.md' was created." in call2.tool_results[0]


def test_tool_effect_create_file_already_exists(vault: Path, fake_llm: FakeLLM):
    target = vault / "Overview.md"
    orig_content = target.read_text(encoding="utf-8")

    fake_llm.script(
        "Chat",
        tool_calls(("create_file", {"path": "Overview.md", "content": "Doppelt"})),
        final({"reply": "Konnte nicht erstellt werden, existiert schon."}),
    )

    session = start_wiki_chat("Create Overview.md")
    assert session.is_successful
    assert target.read_text(encoding="utf-8") == orig_content
    call2 = fake_llm.last_call("Chat")
    assert "already exists" in call2.tool_results[0]


def test_tool_effect_create_file_with_new_folder(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("create_file", {"path": "New/Sub/X.md", "content": "Content X"})),
        final({"reply": "File created in the new folder."}),
    )

    session = start_wiki_chat("Create New/Sub/X.md")
    assert session.is_successful
    target = vault / "New" / "Sub" / "X.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "Content X\n"


def test_tool_effect_create_directory_success(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("create_directory", {"path": "New/Folder"})),
        final({"reply": "Folder created."}),
    )
    session = start_wiki_chat("Create folder New/Folder")
    assert session.is_successful
    assert (vault / "New" / "Folder").is_dir()
    call2 = fake_llm.last_call("Chat")
    assert "Folder 'New/Folder' was created." in call2.tool_results[0]


def test_tool_effect_create_directory_already_exists(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("create_directory", {"path": "Meetings"})),
        final({"reply": "The folder already exists."}),
    )
    session = start_wiki_chat("Create the Meetings folder again")
    assert session.is_successful
    call2 = fake_llm.last_call("Chat")
    assert "already exists" in call2.tool_results[0]


def test_tool_effect_edit_file_success(vault: Path, fake_llm: FakeLLM):
    target = vault / "Architecture" / "Data-Pipeline.md"
    orig_text = target.read_text(encoding="utf-8")
    assert "---" in orig_text

    fake_llm.script(
        "Chat",
        tool_calls(("edit_file", {"path": "Architecture/Data-Pipeline.md", "content": "New pipeline text"})),
        final({"reply": "Data-Pipeline aktualisiert."}),
    )
    session = start_wiki_chat("Edit Data-Pipeline.md")
    assert session.is_successful
    new_text = target.read_text(encoding="utf-8")
    assert "New pipeline text" in new_text
    assert new_text.startswith("---\n")  # Frontmatter preserved


def test_tool_effect_edit_file_failure_nonexistent(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("edit_file", {"path": "DoesNotExist.md", "content": "Text"})),
        final({"reply": "File not found."}),
    )
    session = start_wiki_chat("Edit DoesNotExist.md")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "No file" in call.tool_results[0]


def test_tool_effect_move_file_success(vault: Path, fake_llm: FakeLLM):
    source = vault / "Meetings" / "Weekly-Sync.md"
    content = source.read_text(encoding="utf-8")
    dest = vault / "Meetings" / "Moved.md"

    fake_llm.script(
        "Chat",
        tool_calls(("move_file", {"path": "Meetings/Weekly-Sync.md", "new_path": "Meetings/Moved.md"})),
        final({"reply": "File moved."}),
    )
    session = start_wiki_chat("Move Weekly-Sync.md")
    assert session.is_successful
    assert not source.exists()
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == content


def test_tool_effect_move_file_failure_dest_exists(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("move_file", {"path": "Meetings/Weekly-Sync.md", "new_path": "Overview.md"})),
        final({"reply": "Ziel existiert schon."}),
    )
    session = start_wiki_chat("Move onto Overview")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "already exists" in call.tool_results[0]


def test_tool_effect_delete_file_success(vault: Path, fake_llm: FakeLLM):
    target = vault / "Meetings" / "Weekly-Sync.md"
    assert target.exists()

    fake_llm.script(
        "Chat",
        tool_calls(("delete_file", {"path": "Meetings/Weekly-Sync.md"})),
        final({"reply": "File deleted."}),
    )
    session = start_wiki_chat("Delete Weekly-Sync.md")
    assert session.is_successful
    assert not target.exists()


def test_tool_effect_delete_file_failure_nonexistent(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("delete_file", {"path": "DoesNotExistAtAll.md"})),
        final({"reply": "War schon weg."}),
    )
    session = start_wiki_chat("Delete DoesNotExist")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "No file" in call.tool_results[0]


def test_tool_effect_load_files_leaves_vault_unchanged(vault: Path, fake_llm: FakeLLM):
    snapshot_before = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}

    fake_llm.script(
        "Chat",
        tool_calls(("load_files", {"paths": ["Overview.md"]})),
        final({"reply": "Ich habe die Overview gelesen."}),
    )
    session = start_wiki_chat("Lies Overview")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Overview" in call.tool_results[0]

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
        final({"answer": "The milestones are listed in the overview.", "sources": ["Overview.md"]}),
    )

    session = start_wiki_chat("Gibt es Hyperraum?")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "The milestones are listed in the overview." in call.tool_results[0]
    assert "Sources: Overview.md" in call.tool_results[0]
    assert "Full text of the cited sources" in call.tool_results[0]


def test_tool_effect_ask_librarian_failure(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(("ask_librarian", {"question": "Unknownes Thema?"})),
        final({"reply": "Der Librarian konnte nichts finden."}),
    )
    fake_llm.script(
        "Librarian",
        RuntimeError("Librarian crash"),
    )
    session = start_wiki_chat("Frag Librarian nach Fehler")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Error: the librarian" in call.tool_results[0]


def test_tool_effect_web_search(vault: Path, fake_llm: FakeLLM, fake_genai):
    fake_genai.text = "Daily batch remains common for internal analytics."
    fake_genai.sources = [("NASA", "https://nasa.gov/warp")]

    fake_llm.script(
        "Chat",
        tool_calls(("web_search", {"query": "daily batch ingestion"})),
        final({"reply": "According to the web search, daily batch is still standard."}),
    )

    session = start_wiki_chat("Research batch ingestion")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Daily batch remains common" in call.tool_results[0]
    assert "https://nasa.gov/warp" in call.tool_results[0]


def test_tool_effect_deep_reasoning_includes_file_context(vault: Path, fake_llm: FakeLLM, fake_antigravity):
    fake_antigravity.reply = "Detaillierte Analyse zu gesellschaftlichen Folgen."

    fake_llm.script(
        "Chat",
        tool_calls(("deep_reasoning", {"task": "Analysiere Meetings", "file_paths": ["Overview.md"]})),
        final({"reply": "Hier ist die Tiefenanalyse."}),
    )

    session = start_wiki_chat("Analysiere Meetings mit Overview")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Detaillierte Analyse" in call.tool_results[0]

    assert len(fake_antigravity.prompts) == 1
    assert "Analysiere Meetings" in fake_antigravity.prompts[0]
    assert "## Context from the vault" in fake_antigravity.prompts[0]
    assert "Overview.md" in fake_antigravity.prompts[0]


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
        tool_calls(("start_background_task", {"description": "Large review of every meeting note"})),
        final({"reply": "Hintergrund-Aufgabe gestartet."}),
    )

    session = start_wiki_chat("Start a background task")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Background task started (task_id:" in call.tool_results[0]
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
    session = start_wiki_chat("Check the status of test_tid")
    assert session.is_successful
    call = fake_llm.last_call("Chat")
    assert "Status: done" in call.tool_results[0]

    # Check unknown ID
    fake_llm.script(
        "Chat",
        tool_calls(("check_task_status", {"task_id": "ghost_id"})),
        final({"reply": "ID existiert nicht."}),
    )
    session2 = start_wiki_chat("Check ghost")
    assert session2.is_successful
    call_ghost = fake_llm.last_call("Chat")
    assert "Error: no background task found with the ID 'ghost_id'" in call_ghost.tool_results[0]


def test_tool_effect_multiple_mutations_in_single_turn(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Chat",
        tool_calls(
            ("create_directory", {"path": "MultiDir"}),
            ("create_file", {"path": "MultiDir/File.md", "content": "Multi content"}),
        ),
        final({"reply": "Folder and file created."}),
    )

    session = start_wiki_chat("Create MultiDir and MultiDir/File.md")
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
        final({"reply": "I created the file Meetings/Hallucinated.md!"}),
        tool_calls(("create_file", {"path": "Meetings/Hallucinated.md", "content": "Jetzt wirklich"})),
        final({"reply": "Jetzt ist Meetings/Hallucinated.md angelegt."}),
    )

    session = start_wiki_chat("Create Meetings/Hallucinated.md")
    assert session.is_successful
    calls = fake_llm.calls_for("Chat")
    assert len(calls) == 3
    assert "Your response was rejected" in calls[1].last_user_message
    assert (vault / "Meetings" / "Hallucinated.md").exists()
    assert (vault / "Meetings" / "Hallucinated.md").read_text(encoding="utf-8") == "Jetzt wirklich\n"
