from pathlib import Path
import pytest

from src.agentic.agents.librarian import (
    LibrarianAgent,
    ask_librarian,
)
from src.agentic.engine.model_rotation import LIBRARIAN_MODELS as _MODEL_ROTATION
from src.schemas.librarian_schema import LibrarianOutput
from src.tests.fakes.fake_llm import FakeLLM, final, tool_calls


def test_librarian_input_contains_question_and_ai_map(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Librarian",
        final({"answer": "Terra ist ein alter Name.", "sources": ["Overview.md"]}),
    )

    session = ask_librarian("Was bedeutet Terra?")
    assert session.is_successful
    call = fake_llm.calls_for("Librarian")[0]
    # Input JSON in user message contains question and ai_map
    assert "Was bedeutet Terra?" in call.last_user_message
    assert "Overview.md" in call.last_user_message or "ai_map" in call.last_user_message
    assert isinstance(session.final_result, LibrarianOutput)


@pytest.mark.parametrize(
    "tool_name, tool_args, expected_result_substr",
    [
        ("load_directory_summaries", {"paths": ["Meetings"]}, "Meetings"),
        ("load_file_summaries", {"paths": ["Overview.md"]}, "Overview.md"),
        ("load_files", {"paths": ["Overview.md"]}, "Overview.md"),
    ],
)
def test_librarian_tools_effect(vault: Path, fake_llm: FakeLLM, tool_name: str, tool_args: dict, expected_result_substr: str):
    fake_llm.script(
        "Librarian",
        tool_calls((tool_name, tool_args)),
        final({"answer": f"Recherche via {tool_name} abgeschlossen.", "sources": []}),
    )

    session = ask_librarian(f"Recherchiere mit {tool_name}")
    assert session.is_successful
    call2 = fake_llm.last_call("Librarian")
    assert expected_result_substr in call2.tool_results[0]


def test_librarian_model_rotation(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "Librarian",
        final({"answer": "Antwort 1", "sources": []}),
        final({"answer": "Antwort 2", "sources": []}),
    )

    ask_librarian("Frage 1")
    ask_librarian("Frage 2")

    calls = fake_llm.calls_for("Librarian")
    assert len(calls) == 2
    assert calls[0].model != calls[1].model
    assert calls[0].model in [str(m) for m in _MODEL_ROTATION]
    assert calls[1].model in [str(m) for m in _MODEL_ROTATION]
