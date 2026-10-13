import time
from pathlib import Path
import pytest

from src.agentic.agents import task_agent
from src.agentic.agents.task_agent import (
    TaskAgent,
    check_task_status,
    start_background_task,
    _jobs,
    _MODEL_ROTATION,
)
from src.schemas.llm_models import LLMModels
from src.agentic.tools import CONTENT_TOOLS
from src.tests.fakes.fake_llm import FakeLLM, final, raw, tool_calls


def test_task_agent_full_lifecycle(vault: Path, fake_llm: FakeLLM, sync_threads):
    def update_plan_step1(kwargs):
        tid = list(_jobs.keys())[-1]
        return tool_calls(("update_plan", {"task_id": tid, "steps": [
            {"step": "Erstelle Notiz", "status": "in_progress"},
            {"step": "Abschluss", "status": "pending"},
        ]}))

    def update_plan_step2(kwargs):
        tid = list(_jobs.keys())[-1]
        return tool_calls(("update_plan", {"task_id": tid, "steps": [
            {"step": "Erstelle Notiz", "status": "done"},
            {"step": "Abschluss", "status": "done"},
        ]}))

    fake_llm.script(
        "TaskAgent",
        update_plan_step1,
        tool_calls(("create_file", {"path": "Kulturen/TaskOutput.md", "content": "Generiert"})),
        update_plan_step2,
        final({"summary": "Alle Arbeitsschritte erfolgreich ausgeführt."}),
    )

    msg = start_background_task("Erstelle TaskOutput.md und berichte")
    assert "task_id:" in msg
    tid = list(_jobs.keys())[-1]
    job = _jobs[tid]

    assert job.status == "done"
    assert len(job.plan) == 2
    assert job.plan[0]["status"] == "done"
    assert (vault / "Kulturen" / "TaskOutput.md").exists()

    status_report = check_task_status(tid)
    assert "[x] Erstelle Notiz" in status_report
    assert "[x] Abschluss" in status_report
    assert "Alle Arbeitsschritte erfolgreich ausgeführt." in status_report


def test_task_agent_immediate_final_rejected_and_fails_on_exhaustion(fake_llm: FakeLLM, sync_threads):
    # Max retries is 3, so 4 attempts total
    fake_llm.script(
        "TaskAgent",
        final({"summary": "Halluzinierter Soforterfolg 1"}),
        final({"summary": "Halluzinierter Soforterfolg 2"}),
        final({"summary": "Halluzinierter Soforterfolg 3"}),
        final({"summary": "Halluzinierter Soforterfolg 4"}),
    )

    start_background_task("Aufgabe ohne Tools")
    tid = list(_jobs.keys())[-1]
    job = _jobs[tid]

    assert job.status == "error"
    assert job.error is not None
    assert "Iterationslimit oder wiederholt ungültige Antwort" in job.error
    assert "Fehler:" in check_task_status(tid)


def test_task_agent_update_plan_unknown_task_id(fake_llm: FakeLLM, sync_threads):
    def update_plan_unknown(kwargs):
        return tool_calls(("update_plan", {"task_id": "ghost_tid", "steps": [{"step": "1", "status": "done"}]}))

    fake_llm.script(
        "TaskAgent",
        update_plan_unknown,
        final({"summary": "Abgebrochen"}),
    )

    start_background_task("Aufgabe mit falscher ID")
    call = fake_llm.last_call("TaskAgent")
    assert "Fehler: Unbekannte task_id 'ghost_tid'" in call.tool_results[0]


@pytest.mark.parametrize(
    "tool_name, tool_args, expected_result_substr",
    [
        ("load_files", {"paths": ["Grundannahmen.md"]}, "Grundannahmen.md"),
        ("create_directory", {"path": "TaskDir"}, "erstellt"),
        ("create_file", {"path": "TaskDir/Note.md", "content": "Note"}, "erstellt"),
        ("edit_file", {"path": "Grundannahmen.md", "content": "New"}, "aktualisiert"),
        ("move_file", {"path": "Grundannahmen.md", "new_path": "GrundNeu.md"}, "verschoben"),
        ("delete_file", {"path": "Kulturen/Beispielvolk.md"}, "gelöscht"),
    ],
)
def test_task_agent_content_tools_execution(
    vault: Path, fake_llm: FakeLLM, sync_threads, tool_name: str, tool_args: dict, expected_result_substr: str
):
    def update_plan_fn(kwargs):
        tid = list(_jobs.keys())[-1]
        return tool_calls(("update_plan", {"task_id": tid, "steps": [{"step": "Init", "status": "in_progress"}]}))

    fake_llm.script(
        "TaskAgent",
        update_plan_fn,
        tool_calls((tool_name, tool_args)),
        final({"summary": f"Tool {tool_name} ausgeführt"}),
    )

    start_background_task(f"Test tool {tool_name}")
    call = fake_llm.last_call("TaskAgent")
    assert any(expected_result_substr in r for r in call.tool_results)


def test_task_agent_run_session_exception_handled(fake_llm: FakeLLM, sync_threads):
    fake_llm.script("TaskAgent", RuntimeError("Unrecoverable LLM crash"))

    start_background_task("Crashed Task")
    tid = list(_jobs.keys())[-1]
    job = _jobs[tid]

    assert job.status == "error"
    assert job.error is not None
    assert job.finished_at is not None


def test_task_agent_model_override(fake_llm: FakeLLM, sync_threads):
    def update_plan_fn(kwargs):
        tid = list(_jobs.keys())[-1]
        return tool_calls(("update_plan", {"task_id": tid, "steps": [{"step": "1", "status": "done"}]}))

    fake_llm.script(
        "TaskAgent",
        update_plan_fn,
        final({"summary": "Override Fertig"}),
    )

    start_background_task("Override Model", model_override=LLMModels.GEMMA_31B)
    call = fake_llm.calls_for("TaskAgent")[0]
    assert call.model == str(LLMModels.GEMMA_31B)


def test_task_agent_model_rotation(fake_llm: FakeLLM, sync_threads):
    def update_plan_fn(kwargs):
        tid = list(_jobs.keys())[-1]
        return tool_calls(("update_plan", {"task_id": tid, "steps": [{"step": "1", "status": "done"}]}))

    fake_llm.script(
        "TaskAgent",
        update_plan_fn,
        final({"summary": "Job 1"}),
        update_plan_fn,
        final({"summary": "Job 2"}),
    )

    start_background_task("Job 1")
    start_background_task("Job 2")

    calls = fake_llm.calls_for("TaskAgent")
    # First job calls with model 1, second job calls with model 2
    model1 = calls[0].model
    model2 = calls[2].model
    assert model1 != model2
    assert model1 in [str(m) for m in _MODEL_ROTATION]
    assert model2 in [str(m) for m in _MODEL_ROTATION]


def test_task_agent_forced_final_at_iteration_limit(fake_llm: FakeLLM, sync_threads):
    # TaskAgent has max_tool_iterations = 40.
    # At step 39 (max_tool_iterations - 1), force_final_answer is triggered.
    responses = []
    # 39 tool call responses
    for i in range(39):
        def _step_fn(kwargs, step_num=i):
            tid = list(_jobs.keys())[-1]
            return tool_calls(("update_plan", {"task_id": tid, "steps": [{"step": f"Step {step_num}", "status": "in_progress"}]}))
        responses.append(_step_fn)

    responses.append(final({"summary": "Erzwungener Abschlussbericht"}))

    fake_llm.script("TaskAgent", *responses)

    start_background_task("Langer 40-Runden Task")
    tid = list(_jobs.keys())[-1]
    job = _jobs[tid]

    assert job.status == "done"
    calls = fake_llm.calls_for("TaskAgent")
    assert len(calls) == 40
    # Last call must have no tools
    assert calls[-1].tools == []
    assert job.session.final_result.summary == "Erzwungener Abschlussbericht"


def test_task_agent_real_thread_execution(vault: Path, fake_llm: FakeLLM):
    """Test without sync_threads: runs in real background threading.Thread."""
    def update_plan_fn(kwargs):
        tid = list(_jobs.keys())[-1]
        return tool_calls(("update_plan", {"task_id": tid, "steps": [{"step": "Real thread", "status": "done"}]}))

    fake_llm.script(
        "TaskAgent",
        update_plan_fn,
        final({"summary": "Echter Thread fertig"}),
    )

    msg = start_background_task("Echter Thread Test")
    assert "task_id:" in msg
    tid = list(_jobs.keys())[-1]
    job = _jobs[tid]

    # Poll with timeout
    start_time = time.time()
    while job.status == "running" and time.time() - start_time < 5.0:
        time.sleep(0.05)

    assert job.status == "done"
    assert "Echter Thread fertig" in check_task_status(tid)
