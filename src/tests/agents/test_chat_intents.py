from pathlib import Path
import pytest

from src.agentic.agents.chat import ChatAgent, start_wiki_chat
from src.tests.fakes.fake_llm import FakeLLM, final


@pytest.mark.parametrize(
    "message, expected_substr",
    [
        ("Create a file in the Meetings folder with the content abc", "Meetings"),
        ("Please add a file Cache.md under Architecture/Runtime: 'the cache is in-process'", "Cache.md"),
        ("New note in Reviews/Q1 called Summary with the content Background", "Reviews/Q1"),
    ],
)
def test_create_file_intent_reaches_chat_llm(vault: Path, fake_llm: FakeLLM, message: str, expected_substr: str):
    fake_llm.script("Chat", final({"reply": "On it"}))
    start_wiki_chat(message)

    calls = fake_llm.calls_for("Chat")
    assert len(calls) == 1
    call = calls[0]
    assert message in call.last_user_message
    assert "create_file" in call.tool_names
    assert "create_directory" in call.tool_names

    schema = call.tool_schema("create_file")
    assert "path" in schema["parameters"]["properties"]
    assert "content" in schema["parameters"]["properties"]

    assert "## Current vault overview (ai_map)" in call.system_prompt


def test_active_file_header_prepended_to_user_message(vault: Path, fake_llm: FakeLLM):
    fake_llm.script("Chat", final({"reply": "Noted"}))
    start_wiki_chat(
        "Add a section here",
        active_file="Overview.md",
        active_file_summary="Project goals and milestones",
    )

    call = fake_llm.calls_for("Chat")[0]
    assert "[Note open in editor: Overview.md" in call.last_user_message
    assert "Project goals and milestones" in call.last_user_message
    assert "Add a section here" in call.last_user_message


@pytest.mark.parametrize(
    "intent_message, required_tools",
    [
        ("Edit Overview.md and add a risks section", ["edit_file"]),
        ("Move Meetings/Weekly-Sync.md to Archive/Old.md", ["move_file"]),
        ("Delete the note Architecture/Data-Pipeline.md", ["delete_file"]),
        ("What does the vault say about the deployment process?", ["load_files", "ask_librarian"]),
        ("Is daily batch ingestion still considered good practice?", ["web_search"]),
        ("Think carefully about the long-term consequences of this schema choice", ["deep_reasoning"]),
        ("Start a background task that reviews every meeting note", ["start_background_task", "check_task_status"]),
    ],
)
def test_various_user_intents_reach_chat_llm_with_matching_tools(
    vault: Path, fake_llm: FakeLLM, intent_message: str, required_tools: list[str]
):
    fake_llm.script("Chat", final({"reply": "Understood"}))
    start_wiki_chat(intent_message)

    call = fake_llm.calls_for("Chat")[0]
    assert intent_message in call.last_user_message
    for tool_name in required_tools:
        assert tool_name in call.tool_names
