# src/tests/engine/test_guards.py
from types import SimpleNamespace
import pytest

from src.agentic.engine.guards import (
    check_hallucinated_mutation,
    check_skipped_required_tool,
)
from src.schemas.status import AgentStatus


def _dummy_tool(name: str):
    return SimpleNamespace(name=name)


def _dummy_agent(require_tool_call_first_round: bool = False, tool_names: list[str] | None = None):
    tools = [_dummy_tool(n) for n in (tool_names or [])]
    return SimpleNamespace(
        name="DummyAgent",
        require_tool_call_first_round=require_tool_call_first_round,
        tools=tools,
    )


def _dummy_parse_result(reply: str, status: AgentStatus = AgentStatus.SUCCESS):
    return SimpleNamespace(
        status=status,
        parsed_data=SimpleNamespace(reply=reply),
    )


# ---------------------------------------------------------------------------
# check_skipped_required_tool
# ---------------------------------------------------------------------------

def test_skipped_required_tool_triggers_when_required_and_zero_steps():
    agent = _dummy_agent(require_tool_call_first_round=True)
    assert check_skipped_required_tool(agent, tool_steps=0) is True


def test_skipped_required_tool_false_when_steps_taken():
    agent = _dummy_agent(require_tool_call_first_round=True)
    assert check_skipped_required_tool(agent, tool_steps=1) is False


def test_skipped_required_tool_false_when_not_required():
    agent = _dummy_agent(require_tool_call_first_round=False)
    assert check_skipped_required_tool(agent, tool_steps=0) is False


# ---------------------------------------------------------------------------
# check_hallucinated_mutation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "claim",
    [
        "Ich habe die Datei Kulturen/Apiden.md angelegt.",
        "Ich erstelle die Datei Technologie/Antriebe.md für dich.",
        "Ich habe die Notiz gelöscht und den Ordner geleert.",
        "Ich habe die Datei gespeichert und verschoben.",
    ],
)
def test_hallucinated_mutation_detects_unexecuted_mutation_claims(claim: str):
    agent = _dummy_agent(tool_names=["create_file", "edit_file", "delete_file"])
    parse_result = _dummy_parse_result(reply=claim)
    assert check_hallucinated_mutation(agent, parse_result, tool_steps=0) is True


@pytest.mark.parametrize(
    "negated_claim",
    [
        "Ich habe die Datei nicht angelegt, weil noch Informationen fehlen.",
        "Es wurde keine Datei erstellt.",
        "Ich konnte die Datei nicht finden oder bearbeiten.",
        "Die Datei wurde nicht gelöscht.",
    ],
)
def test_hallucinated_mutation_ignores_negated_claims(negated_claim: str):
    agent = _dummy_agent(tool_names=["create_file", "edit_file"])
    parse_result = _dummy_parse_result(reply=negated_claim)
    assert check_hallucinated_mutation(agent, parse_result, tool_steps=0) is False


def test_hallucinated_mutation_false_if_tool_steps_taken():
    agent = _dummy_agent(tool_names=["create_file"])
    parse_result = _dummy_parse_result(reply="Ich habe die Datei erstellt.")
    # tool_steps > 0 means a tool was actually executed
    assert check_hallucinated_mutation(agent, parse_result, tool_steps=1) is False


def test_hallucinated_mutation_false_if_agent_has_no_mutation_tools():
    agent = _dummy_agent(tool_names=["load_files", "ask_librarian"])
    parse_result = _dummy_parse_result(reply="Ich habe die Datei erstellt.")
    assert check_hallucinated_mutation(agent, parse_result, tool_steps=0) is False


def test_hallucinated_mutation_false_if_parse_status_not_success():
    agent = _dummy_agent(tool_names=["create_file"])
    parse_result = _dummy_parse_result(reply="Ich habe die Datei erstellt.", status=AgentStatus.ERROR)
    assert check_hallucinated_mutation(agent, parse_result, tool_steps=0) is False


def test_hallucinated_mutation_false_for_normal_conversation():
    agent = _dummy_agent(tool_names=["create_file", "edit_file"])
    parse_result = _dummy_parse_result(reply="Hallo! Was kann ich heute für dich tun?")
    assert check_hallucinated_mutation(agent, parse_result, tool_steps=0) is False
