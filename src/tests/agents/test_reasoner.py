from pathlib import Path
import pytest

from src.agentic.agents.reasoner import (
    MODEL,
    SYSTEM_INSTRUCTIONS,
    run_reasoning,
    _build_config,
)


def test_reasoner_sends_task_and_config(fake_antigravity):
    fake_antigravity.reply = "Detailed consideration."

    res = run_reasoning("Analysiere das Paradoxon.")
    assert res == "Detailed consideration."
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

    res = run_reasoning("Explain the architecture", file_paths=["Overview.md"])
    assert res == "Antwort mit Kontext."
    prompt = fake_antigravity.prompts[0]
    assert "Explain the architecture" in prompt
    assert "## Context from the vault" in prompt
    assert "Overview.md" in prompt


def test_reasoner_empty_response(fake_antigravity):
    fake_antigravity.reply = ""

    res = run_reasoning("Leere Frage")
    assert "Error: the reasoning agent returned no answer." in res


def test_reasoner_exception_handled(fake_antigravity):
    fake_antigravity.exc = TimeoutError("Thinking timeout")

    res = run_reasoning("Fehlgeschlagene Frage")
    assert "Error: the reasoning agent could not process the task" in res
    assert "Thinking timeout" in res
