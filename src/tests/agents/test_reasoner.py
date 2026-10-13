from pathlib import Path
import pytest

from src.agentic.agents.reasoner import (
    MODEL,
    SYSTEM_INSTRUCTIONS,
    run_reasoning,
    _build_config,
)


def test_reasoner_sends_task_and_config(fake_antigravity):
    fake_antigravity.reply = "Ausführliche Überlegung."

    res = run_reasoning("Analysiere das Paradoxon.")
    assert res == "Ausführliche Überlegung."
    assert fake_antigravity.prompts == ["Analysiere das Paradoxon."]

    # Check config passed
    assert len(fake_antigravity.configs) == 1
    config = fake_antigravity.configs[0]
    assert config.model.name == MODEL
    assert config.capabilities.enabled_tools == []
    assert config.workspaces == []
    assert config.system_instructions == SYSTEM_INSTRUCTIONS


def test_reasoner_includes_file_paths_as_context(vault: Path, fake_antigravity):
    fake_antigravity.reply = "Antwort mit Kontext."

    res = run_reasoning("Erkläre Technologie", file_paths=["Grundannahmen.md"])
    assert res == "Antwort mit Kontext."
    prompt = fake_antigravity.prompts[0]
    assert "Erkläre Technologie" in prompt
    assert "## Kontext aus dem Wiki" in prompt
    assert "Grundannahmen.md" in prompt


def test_reasoner_empty_response(fake_antigravity):
    fake_antigravity.reply = ""

    res = run_reasoning("Leere Frage")
    assert "Fehler: Der Denk-Agent lieferte keine Antwort." in res


def test_reasoner_exception_handled(fake_antigravity):
    fake_antigravity.exc = TimeoutError("Thinking timeout")

    res = run_reasoning("Fehlgeschlagene Frage")
    assert "Fehler: Der Denk-Agent konnte die Aufgabe nicht bearbeiten" in res
    assert "Thinking timeout" in res
