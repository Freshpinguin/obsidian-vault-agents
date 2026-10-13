import importlib
import pkgutil
from pathlib import Path
import pytest

from src.agentic.agents.chat import ChatAgent, start_wiki_chat
from src.agentic.agents.task_agent import TaskAgent, start_background_task, _jobs, _MODEL_ROTATION as TASK_ROTATION
from src.agentic.agents.librarian import LibrarianAgent, ask_librarian, _MODEL_ROTATION as LIBRARIAN_ROTATION
from src.agentic.agents.summarizer import SummarizerAgent
from src.agentic.agents.folder_summarizer import FolderSummarizerAgent
from src.agentic.engine.compaction import maybe_compact, context_size_chars
from src.agentic.agents.web_search import web_search, MODEL as WEB_SEARCH_MODEL
from src.agentic.agents.reasoner import run_reasoning, MODEL as REASONER_MODEL
from src.core.obsidian_processor import process_obsidian_file, process_folder_summary
from src.schemas.agent_schema import AgentSession, MessageRole, SessionMessage, ToolCall, WikiAgent
from src.schemas.folder_summarizer_schema import FolderSummarizerOutput
from src.schemas.summarizer_schema import SummarizerOutput
from src.tests.fakes.fake_llm import FakeLLM, final, raw, tool_calls
from src.core.logging_config import SessionLogger


EXPECTED_WIKI_AGENTS = {"Chat", "TaskAgent", "Librarian", "Summarizer", "FolderSummarizer"}


def test_meta_all_wiki_agents_registered():
    """Findet per Introspektion alle WikiAgent-Instanzen in src.agentic.agents und prüft,
    dass jeder Agent in EXPECTED_WIKI_AGENTS vorkommt."""
    import src.agentic.agents as agents_pkg

    found_agents = {}
    for _, module_name, _ in pkgutil.iter_modules(agents_pkg.__path__):
        mod = importlib.import_module(f"src.agentic.agents.{module_name}")
        for attr_name in dir(mod):
            val = getattr(mod, attr_name)
            if isinstance(val, WikiAgent):
                found_agents[val.name] = val

    assert set(found_agents.keys()) == EXPECTED_WIKI_AGENTS, (
        f"Gefundene Agenten: {set(found_agents.keys())} != Erwartete: {EXPECTED_WIKI_AGENTS}"
    )


def test_smoke_chat_agent(vault: Path, fake_llm: FakeLLM):
    fake_llm.script("Chat", final({"reply": "Hallo zurück!"}))
    session = start_wiki_chat("Hallo")

    assert session.is_successful
    calls = fake_llm.calls_for("Chat")
    assert len(calls) == 1
    call = calls[0]
    assert call.system_prompt.startswith(ChatAgent.system_prompt)
    assert "## Aktuelle Vault-Übersicht (ai_map)" in call.system_prompt
    assert set(call.tool_names) == {t.name for t in ChatAgent.tools}


def test_smoke_task_agent(vault: Path, fake_llm: FakeLLM, sync_threads):
    def update_plan_callable(kwargs):
        active_task_id = list(_jobs.keys())[-1]
        return tool_calls(("update_plan", {"task_id": active_task_id, "steps": [{"step": "1", "status": "done"}]}))

    fake_llm.script(
        "TaskAgent",
        update_plan_callable,
        final({"summary": "Aufgabe erledigt"}),
    )

    start_background_task("Plane neue Kolonie")
    calls = fake_llm.calls_for("TaskAgent")
    assert len(calls) == 2
    assert calls[0].system_prompt.startswith(TaskAgent.system_prompt)
    assert calls[0].kwargs.get("tool_choice") == "required"
    assert calls[0].model in [str(m) for m in TASK_ROTATION]
    assert "update_plan" in calls[0].tool_names


def test_smoke_librarian(vault: Path, fake_llm: FakeLLM):
    fake_llm.script("Librarian", final({"answer": "Terra existiert.", "sources": ["Grundannahmen.md"]}))
    session = ask_librarian("Gibt es Terra?")

    assert session.is_successful
    calls = fake_llm.calls_for("Librarian")
    assert len(calls) == 1
    call = calls[0]
    assert call.system_prompt.startswith(LibrarianAgent.system_prompt)
    assert call.model in [str(m) for m in LIBRARIAN_ROTATION]
    assert set(call.tool_names) == {"load_directory_summaries", "load_file_summaries", "load_files"}


def test_smoke_summarizer(vault: Path, fake_llm: FakeLLM):
    # Summarizer -> triggers FolderSummarizer on parent
    fake_llm.script(
        "Summarizer",
        final({"document_summary": "Neue Notiz Zusammenfassung", "filemap_summary": "Kurzfassung"}),
    )
    fake_llm.script(
        "FolderSummarizer",
        final({"folder_summary": "Ordner Zusammenfassung", "dirmap_summary": "Ordner kurz"}),
    )

    res = process_obsidian_file(vault, vault / "Grundannahmen.md")
    assert res is True

    calls_sum = fake_llm.calls_for("Summarizer")
    assert len(calls_sum) == 1
    call = calls_sum[0]
    assert call.tools == []
    assert call.kwargs.get("response_format") == SummarizerOutput


def test_smoke_folder_summarizer(vault: Path, fake_llm: FakeLLM):
    fake_llm.script(
        "FolderSummarizer",
        final({"folder_summary": "Kulturen Übersicht", "dirmap_summary": "Kulturen kurz"}),
    )

    res = process_folder_summary(vault, vault / "Kulturen")
    assert res is True

    calls = fake_llm.calls_for("FolderSummarizer")
    assert len(calls) == 1
    call = calls[0]
    assert call.tools == []
    assert call.kwargs.get("response_format") == FolderSummarizerOutput


def test_smoke_context_compactor(fake_llm: FakeLLM):
    fake_llm.script("Compactor", raw("Zusammenfassung des bisherigen Fortschritts."))

    # Construct session with large messages exceeding 30,000 chars
    large_text = "A" * 8000
    session = AgentSession(
        agent=TaskAgent,
        first_input=TaskAgent.input_type(task_id="t1", task="large task", ai_map="map"),
    )
    session.start(session.first_input)
    # Add multiple assistant & tool rounds
    for i in range(5):
        session.messages.append(
            SessionMessage(
                role=MessageRole.ASSISTANT,
                content=f"Runde {i}: {large_text}",
                tool_calls=[ToolCall(id=f"c_{i}", tool_name="update_plan", arguments={"steps": []})],
            )
        )
        session.messages.append(
            SessionMessage(role=MessageRole.TOOL, content=f"Ergebnis {i}: {large_text}", tool_call_id=f"c_{i}"),
        )

    assert context_size_chars(session) > TaskAgent.compaction_threshold_chars
    logger = SessionLogger("TaskAgent", session.session_id)
    maybe_compact(session, 1, logger)

    calls = fake_llm.calls_for("Compactor")
    assert len(calls) == 1
    assert calls[0].model == str(TaskAgent.compaction_model)
    assert calls[0].tools == []


def test_smoke_web_search(fake_genai):
    fake_genai.text = "Alcubierre-Antrieb ist theoretisch untersucht."
    fake_genai.sources = [("NASA Breakthrough Propulsion", "https://nasa.gov/warp")]

    res = web_search("Ist Warp realistisch?")
    assert "Alcubierre-Antrieb" in res
    assert "https://nasa.gov/warp" in res
    assert len(fake_genai.calls) == 1
    call = fake_genai.calls[0]
    assert call["model"] == WEB_SEARCH_MODEL
    # Tools contains google_search
    config = call["config"]
    assert any(getattr(t, "google_search", None) is not None for t in config.tools)


def test_smoke_reasoner(fake_antigravity):
    fake_antigravity.reply = "Ausführliche Begründung zur Zeitdilatation."

    res = run_reasoning("Erkläre die Zeitdilatation in unserem Setting.")
    assert res == "Ausführliche Begründung zur Zeitdilatation."
    assert len(fake_antigravity.prompts) == 1
    assert "Zeitdilatation" in fake_antigravity.prompts[0]
