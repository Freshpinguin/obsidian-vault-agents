import os
from pathlib import Path
from pydantic import BaseModel, Field
import pytest
import litellm

from src.agentic.engine.runner import (
    FORCE_FINAL_ANSWER_INSTRUCTION,
    REQUEST_TIMEOUT_S,
    continue_chat_session,
    run_agent_session,
    start_chat_session,
)
from src.schemas.agent_schema import AgentStatus, WikiAgent
from src.schemas.llm_models import FALLBACK_MAP, LLMModels
from src.schemas.tool_schema import WikiTool
from src.tests.fakes.fake_llm import FakeLLM, final, raw, tool_calls, make_tool_call, response
from types import SimpleNamespace as NS


class DummyInput(BaseModel):
    message: str


class DummyOutput(BaseModel):
    reply: str = Field(description="Antwort")


class ToolArgs(BaseModel):
    param: str = Field(description="Param")


@pytest.fixture
def dummy_agent_factory():
    def _create(name="TestEngineAgent", tools=None, **kwargs):
        return WikiAgent(
            name=name,
            system_prompt=f"SYSTEM_PROMPT_FOR_{name}",
            input_type=DummyInput,
            response_type=DummyOutput,
            tools=tools or [],
            **kwargs,
        )
    return _create


def test_e1_final_valid(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory()
    fake_llm.register(agent.name, agent.system_prompt)
    fake_llm.script(agent.name, final({"reply": "Erfolg"}))

    session = run_agent_session(agent, DummyInput(message="Start"))
    assert session.is_successful
    assert len(fake_llm.calls_for(agent.name)) == 1
    assert session.final_result.reply == "Erfolg"
    assert session.log_path is not None
    assert Path(session.log_path).exists()


def test_e2_tool_call_then_final(fake_llm: FakeLLM, dummy_agent_factory):
    recorded_calls = []

    def dummy_func(param: str):
        recorded_calls.append(param)
        return f"Result: {param}"

    tool = WikiTool(name="dummy_tool", description="test", parameters=ToolArgs, func=dummy_func)
    agent = dummy_agent_factory(tools=[tool])
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        tool_calls(("dummy_tool", {"param": "alpha"})),
        final({"reply": "Nach Tool"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert session.is_successful
    assert recorded_calls == ["alpha"]
    calls = fake_llm.calls_for(agent.name)
    assert len(calls) == 2
    # Second call contains tool result
    tool_results = calls[1].tool_results
    assert len(tool_results) == 1
    assert tool_results[0] == "Result: alpha"
    assert [c.status for c in session.history] == [AgentStatus.TOOL_CALL, AgentStatus.SUCCESS]


def test_e3_multiple_tool_calls_in_one_turn(fake_llm: FakeLLM, dummy_agent_factory):
    recorded = []

    def dummy_func(param: str):
        recorded.append(param)
        return f"Echo {param}"

    tool = WikiTool(name="dummy_tool", description="test", parameters=ToolArgs, func=dummy_func)
    agent = dummy_agent_factory(tools=[tool])
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        tool_calls(("dummy_tool", {"param": "first"}), ("dummy_tool", {"param": "second"})),
        final({"reply": "Done"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert session.is_successful
    assert recorded == ["first", "second"]
    calls = fake_llm.calls_for(agent.name)
    assert len(calls) == 2
    assert len(calls[1].tool_results) == 2
    assert calls[1].tool_results == ["Echo first", "Echo second"]


def test_e4_unknown_tool_name(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory(tools=[])
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        tool_calls(("ghost_tool", {"param": "x"})),
        final({"reply": "Recovered"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert session.is_successful
    calls = fake_llm.calls_for(agent.name)
    assert "Error: unknown tool 'ghost_tool'" in calls[1].tool_results[0]


def test_e5_invalid_arguments_json(fake_llm: FakeLLM, dummy_agent_factory):
    tool = WikiTool(name="dummy_tool", description="test", parameters=ToolArgs, func=lambda param: f"Echo {param}")
    agent = dummy_agent_factory(tools=[tool])
    fake_llm.register(agent.name, agent.system_prompt)

    # Invalid json in arguments
    fake_llm.script(
        agent.name,
        tool_calls(("dummy_tool", None, "invalid-json{")),
        final({"reply": "Done"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert session.is_successful
    calls = fake_llm.calls_for(agent.name)
    # Validation error because arguments was parsed as {}
    assert "Error: invalid arguments" in calls[1].tool_results[0]


def test_e6_retry_on_invalid_json(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory(max_retries=2)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        raw("Kein valides JSON"),
        final({"reply": "Jetzt richtig"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert session.is_successful
    calls = fake_llm.calls_for(agent.name)
    assert len(calls) == 2
    assert "The previous response was invalid" in calls[1].last_user_message


def test_e7_max_retries_exhausted(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory(max_retries=2)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        raw("raw 1"),
        raw("raw 2"),
        raw("raw 3"),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert not session.is_successful
    assert len(fake_llm.calls_for(agent.name)) == 3
    assert all(c.status == AgentStatus.ERROR for c in session.history)


def test_e8_json_fence_parsed_correctly(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory()
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(agent.name, raw('```json\n{"reply": "In fence"}\n```'))

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert session.is_successful
    assert session.final_result.reply == "In fence"


def test_e9_api_exception_handled(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory()
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(agent.name, RuntimeError("Provider network timeout"))

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert not session.is_successful
    assert len(session.history) == 1
    assert session.history[0].status == AgentStatus.ERROR
    assert "API error: Provider network timeout" in session.history[0].error_message


def test_e10_forced_final_answer_at_max_tool_iterations(fake_llm: FakeLLM, dummy_agent_factory):
    tool = WikiTool(name="dummy_tool", description="test", parameters=ToolArgs, func=lambda param: "ok")
    agent = dummy_agent_factory(tools=[tool], max_tool_iterations=3)
    fake_llm.register(agent.name, agent.system_prompt)

    # Rounds:
    # 1: tool_steps = 1
    # 2: tool_steps = 2 (max_tool_iterations - 1). force_final_answer becomes True!
    # 3: Next call has no tools, with response_format!
    fake_llm.script(
        agent.name,
        tool_calls(("dummy_tool", {"param": "1"})),
        tool_calls(("dummy_tool", {"param": "2"})),
        final({"reply": "Endlich fertig"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert session.is_successful
    calls = fake_llm.calls_for(agent.name)
    assert len(calls) == 3
    # Call 3 must NOT offer tools
    assert calls[2].tools == []
    assert FORCE_FINAL_ANSWER_INSTRUCTION in calls[2].last_user_message


def test_e11_request_tools_vs_response_format(fake_llm: FakeLLM, dummy_agent_factory):
    tool = WikiTool(name="dummy_tool", description="test", parameters=ToolArgs, func=lambda param: "ok")
    agent_with_tool = dummy_agent_factory(name="WithToolAgent", tools=[tool])
    agent_no_tool = dummy_agent_factory(name="NoToolAgent", tools=[])

    fake_llm.register(agent_with_tool.name, agent_with_tool.system_prompt)
    fake_llm.register(agent_no_tool.name, agent_no_tool.system_prompt)

    fake_llm.script(agent_with_tool.name, final({"reply": "w"}))
    fake_llm.script(agent_no_tool.name, final({"reply": "wo"}))

    run_agent_session(agent_with_tool, DummyInput(message="1"))
    run_agent_session(agent_no_tool, DummyInput(message="2"))

    call_with_tool = fake_llm.calls_for(agent_with_tool.name)[0]
    call_no_tool = fake_llm.calls_for(agent_no_tool.name)[0]

    assert "tools" in call_with_tool.kwargs
    assert "response_format" not in call_with_tool.kwargs

    assert "tools" not in call_no_tool.kwargs
    assert "response_format" in call_no_tool.kwargs


def test_e12_require_tool_choice_first_round(fake_llm: FakeLLM, dummy_agent_factory, monkeypatch):
    tool = WikiTool(name="dummy_tool", description="test", parameters=ToolArgs, func=lambda param: "ok")
    agent = dummy_agent_factory(tools=[tool], require_tool_call_first_round=True)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        tool_calls(("dummy_tool", {"param": "1"})),
        final({"reply": "Done"}),
    )

    run_agent_session(agent, DummyInput(message="1"))
    calls = fake_llm.calls_for(agent.name)
    assert calls[0].kwargs.get("tool_choice") == "required"
    assert "tool_choice" not in calls[1].kwargs

    # Test with supports_tool_choice -> False
    monkeypatch.setattr("src.agentic.engine.runner.supports_tool_choice", lambda model: False)
    fake_llm.script(
        agent.name,
        tool_calls(("dummy_tool", {"param": "2"})),
        final({"reply": "Done 2"}),
    )
    run_agent_session(agent, DummyInput(message="2"))
    call3 = fake_llm.calls_for(agent.name)[2]
    assert "tool_choice" not in call3.kwargs


def test_e13_require_tool_choice_immediate_final_rejected(fake_llm: FakeLLM, dummy_agent_factory):
    tool = WikiTool(name="dummy_tool", description="test", parameters=ToolArgs, func=lambda param: "ok")
    agent = dummy_agent_factory(tools=[tool], require_tool_call_first_round=True)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        final({"reply": "Ich antworte einfach so"}),
        tool_calls(("dummy_tool", {"param": "now"})),
        final({"reply": "Jetzt mit Tool"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))
    assert session.is_successful
    calls = fake_llm.calls_for(agent.name)
    assert len(calls) == 3
    assert "must call at least one tool" in calls[1].last_user_message


def test_e14_hallucinated_mutation_rejected(fake_llm: FakeLLM, dummy_agent_factory, vault: Path):
    mutation_tool = WikiTool(name="create_file", description="create", parameters=ToolArgs, func=lambda param: "ok")
    agent = dummy_agent_factory(tools=[mutation_tool])
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        final({"reply": "I created the file Meetings/Zeta.md!"}),
        tool_calls(("create_file", {"param": "real"})),
        final({"reply": "Datei jetzt wirklich erstellt."}),
    )

    session = run_agent_session(agent, DummyInput(message="Create"))
    assert session.is_successful
    calls = fake_llm.calls_for(agent.name)
    assert len(calls) == 3
    assert "Your response was rejected" in calls[1].last_user_message
    assert "did NOT execute a corresponding tool" in calls[1].last_user_message


def test_e15_mutation_claim_with_negation_accepted(fake_llm: FakeLLM, dummy_agent_factory):
    mutation_tool = WikiTool(name="create_file", description="create", parameters=ToolArgs, func=lambda param: "ok")
    agent = dummy_agent_factory(tools=[mutation_tool])
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        final({"reply": "The file could not be created because the path is missing."}),
    )

    session = run_agent_session(agent, DummyInput(message="Create"))
    assert session.is_successful
    assert len(fake_llm.calls_for(agent.name)) == 1


def test_e16_model_override_and_fallbacks(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory(default_model=LLMModels.GEMMA_31B)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(agent.name, final({"reply": "ok"}))

    run_agent_session(agent, DummyInput(message="Run"), model_override=LLMModels.GEMINI_3_5_FLASH_LITE)
    call = fake_llm.calls_for(agent.name)[0]
    assert call.model == str(LLMModels.GEMINI_3_5_FLASH_LITE)
    # Retry/failover is ours now (see _completion_with_failover), so litellm must not run
    # a chain of its own on top of it.
    assert call.kwargs.get("fallbacks") is None
    assert call.kwargs.get("num_retries") == 0
    assert call.kwargs.get("timeout") == REQUEST_TIMEOUT_S


def test_e16b_tool_call_rotates_tool_fallbacks(fake_llm: FakeLLM, dummy_agent_factory):
    tool = WikiTool(name="dummy_tool", description="test", parameters=ToolArgs, func=lambda param: "ok")
    agent = dummy_agent_factory(default_model=LLMModels.GEMINI_3_5_FLASH_LITE, tools=[tool])
    fake_llm.register(agent.name, agent.system_prompt)

    # The primary model fails hard enough to exhaust its retries, so the turn must fail
    # over to the tool-capable sibling rather than down to a Gemma model.
    fake_llm.script(
        agent.name,
        litellm.InternalServerError("boom", model="x", llm_provider="gemini"),
        litellm.InternalServerError("boom", model="x", llm_provider="gemini"),
        litellm.InternalServerError("boom", model="x", llm_provider="gemini"),
        final({"reply": "done"}),
    )
    session = run_agent_session(agent, DummyInput(message="Run"))

    assert session.is_successful
    models = [c.model for c in fake_llm.calls_for(agent.name)]
    assert models[:3] == [str(LLMModels.GEMINI_3_5_FLASH_LITE)] * 3
    assert models[3] == str(LLMModels.GEMINI_3_1_FLASH_LITE)
    assert all(c.kwargs.get("fallbacks") is None for c in fake_llm.calls_for(agent.name))

    # And when starting with 3.1, the rotation runs the other way round.
    fake_llm.script(
        agent.name,
        litellm.InternalServerError("boom", model="x", llm_provider="gemini"),
        litellm.InternalServerError("boom", model="x", llm_provider="gemini"),
        litellm.InternalServerError("boom", model="x", llm_provider="gemini"),
        final({"reply": "done2"}),
    )
    before = len(fake_llm.calls_for(agent.name))
    run_agent_session(agent, DummyInput(message="Run2"), model_override=LLMModels.GEMINI_3_1_FLASH_LITE)
    models2 = [c.model for c in fake_llm.calls_for(agent.name)[before:]]
    assert models2[:3] == [str(LLMModels.GEMINI_3_1_FLASH_LITE)] * 3
    assert models2[3] == str(LLMModels.GEMINI_3_5_FLASH_LITE)


def test_e17_agent_temperature_passed(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory(temperature=0.7)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(agent.name, final({"reply": "ok"}))

    run_agent_session(agent, DummyInput(message="Run"))
    call = fake_llm.calls_for(agent.name)[0]
    assert call.kwargs.get("temperature") == 0.7


def test_e18_continue_chat_session(fake_llm: FakeLLM, dummy_agent_factory):
    agent = dummy_agent_factory()
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        final({"reply": "Erste Antwort"}),
        final({"reply": "Zweite Antwort"}),
    )

    session = start_chat_session(agent, "Erste Frage")
    sess_id_1 = session.session_id
    log_path_1 = session.log_path

    session = continue_chat_session(session, "Folgefrage")
    assert session.session_id == sess_id_1
    assert session.log_path == log_path_1

    calls = fake_llm.calls_for(agent.name)
    assert len(calls) == 2
    # Second call includes first question, first answer, and second question
    assert calls[1].user_messages == ["Erste Frage", "Folgefrage"]


def test_e24_transient_error_retries_same_model_then_succeeds(fake_llm: FakeLLM, dummy_agent_factory):
    """A transient 500 is retried on the SAME model - every model sits behind one
    provider, so failing over first would inherit the same outage."""
    agent = dummy_agent_factory(default_model=LLMModels.GEMINI_3_5_FLASH_LITE)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        litellm.InternalServerError("boom", model="x", llm_provider="gemini"),
        final({"reply": "recovered"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))

    assert session.is_successful
    assert session.final_result.reply == "recovered"
    models = [c.model for c in fake_llm.calls_for(agent.name)]
    assert models == [str(LLMModels.GEMINI_3_5_FLASH_LITE)] * 2
    # A recovered call must not leave an ERROR record behind.
    assert [c.status for c in session.history] == [AgentStatus.SUCCESS]


def test_e25_rate_limit_fails_over_without_retrying_same_model(fake_llm: FakeLLM, dummy_agent_factory):
    """Quota is counted per model, so a 429 must hand over immediately instead of
    waiting out the same limit twice."""
    agent = dummy_agent_factory(default_model=LLMModels.GEMINI_3_5_FLASH_LITE)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        litellm.RateLimitError("quota", model="x", llm_provider="gemini"),
        final({"reply": "other model"}),
    )

    session = run_agent_session(agent, DummyInput(message="Run"))

    assert session.is_successful
    models = [c.model for c in fake_llm.calls_for(agent.name)]
    assert models == [
        str(LLMModels.GEMINI_3_5_FLASH_LITE),
        str(FALLBACK_MAP[LLMModels.GEMINI_3_5_FLASH_LITE][0]),
    ]


def test_e26_hard_error_fails_fast(fake_llm: FakeLLM, dummy_agent_factory):
    """A bad request is not transient: no retry, no failover - one call, then stop."""
    agent = dummy_agent_factory(default_model=LLMModels.GEMINI_3_5_FLASH_LITE)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(agent.name, litellm.BadRequestError("nope", model="x", llm_provider="gemini"))

    session = run_agent_session(agent, DummyInput(message="Run"))

    assert not session.is_successful
    assert len(fake_llm.calls_for(agent.name)) == 1
    assert session.history[0].status == AgentStatus.ERROR


def test_e27_failed_turn_is_rolled_back(fake_llm: FakeLLM, dummy_agent_factory):
    """A turn that dies before any tool ran must leave the session exactly as it was,
    so the history does not end on a user message with no assistant reply."""
    agent = dummy_agent_factory()
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(
        agent.name,
        final({"reply": "First answer"}),
        litellm.BadRequestError("nope", model="x", llm_provider="gemini"),
        final({"reply": "Second answer"}),
    )

    session = start_chat_session(agent, "First question")
    messages_after_success = list(session.messages)

    continue_chat_session(session, "Doomed question")
    assert not session.is_successful
    assert [m.content for m in session.messages] == [m.content for m in messages_after_success]
    assert "Doomed question" not in [m.content for m in session.messages]

    # The retry therefore starts from clean context and works.
    continue_chat_session(session, "Retried question")
    assert session.is_successful
    assert session.final_result.reply == "Second answer"


def test_e28_retry_budget_caps_total_attempts(fake_llm: FakeLLM, dummy_agent_factory, monkeypatch):
    """The budget stops a bad provider minute from stacking attempts x candidates into
    minutes of waiting - but it never prevents the first attempt."""
    monkeypatch.setattr("src.agentic.engine.runner.CALL_BUDGET_S", 0.0)
    agent = dummy_agent_factory(default_model=LLMModels.GEMINI_3_5_FLASH_LITE)
    fake_llm.register(agent.name, agent.system_prompt)

    fake_llm.script(agent.name, litellm.InternalServerError("boom", model="x", llm_provider="gemini"))

    session = run_agent_session(agent, DummyInput(message="Run"))

    assert not session.is_successful
    assert len(fake_llm.calls_for(agent.name)) == 1
    assert "API error" in session.history[0].error_message
