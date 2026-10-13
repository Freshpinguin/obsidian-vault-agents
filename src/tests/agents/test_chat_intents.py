from pathlib import Path
import pytest

from src.agents.chat import ChatAgent, start_wiki_chat
from src.tests.fakes.fake_llm import FakeLLM, final


@pytest.mark.parametrize(
    "message, expected_substr",
    [
        ("Erstelle ein File unter dem Ordner Kulturen mit dem Inhalt abc", "Kulturen"),
        ("Leg mir bitte unter Technologie/Waffen eine Datei Laser.md an: 'Laser sind heiß'", "Laser.md"),
        ("Neue Notiz in Ären/Frühzeit namens Übersicht mit Inhalt Vorgeschichte", "Ären/Frühzeit"),
    ],
)
def test_create_file_intent_reaches_chat_llm(vault: Path, fake_llm: FakeLLM, message: str, expected_substr: str):
    fake_llm.script("Chat", final({"reply": "Wird erledigt"}))
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

    assert "## Aktuelle Vault-Übersicht (ai_map)" in call.system_prompt


def test_active_file_header_prepended_to_user_message(vault: Path, fake_llm: FakeLLM):
    fake_llm.script("Chat", final({"reply": "Gesehen"}))
    start_wiki_chat(
        "Füge hier einen Abschnitt hinzu",
        active_file="Grundannahmen.md",
        active_file_summary="Physikalische Regeln",
    )

    call = fake_llm.calls_for("Chat")[0]
    assert "[Im Editor geöffnete Notiz: Grundannahmen.md" in call.last_user_message
    assert "Physikalische Regeln" in call.last_user_message
    assert "Füge hier einen Abschnitt hinzu" in call.last_user_message


@pytest.mark.parametrize(
    "intent_message, required_tools",
    [
        ("Bearbeite Grundannahmen.md und ergänze Relativität", ["edit_file"]),
        ("Verschiebe Kulturen/Beispielvolk.md nach Archiv/Alt.md", ["move_file"]),
        ("Lösche die Notiz Technologie/Antriebe.md", ["delete_file"]),
        ("Was weiß der Vault über die Gasgeborenen?", ["load_files", "ask_librarian"]),
        ("Ist der Alcubierre-Antrieb in echter Physik realistisch?", ["web_search"]),
        ("Denk gründlich über die gesellschaftlichen Folgen nach", ["deep_reasoning"]),
        ("Starte eine Hintergrund-Recherche zu allen Alien-Spezies", ["start_background_task", "check_task_status"]),
    ],
)
def test_various_user_intents_reach_chat_llm_with_matching_tools(
    vault: Path, fake_llm: FakeLLM, intent_message: str, required_tools: list[str]
):
    fake_llm.script("Chat", final({"reply": "Verstanden"}))
    start_wiki_chat(intent_message)

    call = fake_llm.calls_for("Chat")[0]
    assert intent_message in call.last_user_message
    for tool_name in required_tools:
        assert tool_name in call.tool_names
