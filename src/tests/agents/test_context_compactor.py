import pytest

from src.agents.context_compactor import maybe_compact, context_size_chars
from src.agents.task_agent import TaskAgent
from src.core.logging_config import SessionLogger
from src.schemas.agent_schema import (
    AgentSession,
    MessageRole,
    SessionMessage,
    ToolCall,
    WikiAgent,
)
from src.schemas.task_agent_schema import TaskAgentInput, TaskAgentOutput
from src.tests.fakes.fake_llm import FakeLLM, raw


def _create_session_with_turns(agent: WikiAgent, num_turns: int, char_multiplier: int = 1000):
    session = AgentSession(
        agent=agent,
        first_input=TaskAgentInput(task_id="t1", task="test task", ai_map="map"),
    )
    session.start(session.first_input)
    content_fill = "X" * char_multiplier

    for i in range(num_turns):
        session.messages.append(
            SessionMessage(
                role=MessageRole.ASSISTANT,
                content=f"Turn {i}: {content_fill}",
                tool_calls=[ToolCall(id=f"c_{i}", tool_name="update_plan", arguments={"step": i})],
            )
        )
        session.messages.append(
            SessionMessage(
                role=MessageRole.TOOL,
                content=f"Result {i}: {content_fill}",
                tool_call_id=f"c_{i}",
                tool_name="update_plan",
            )
        )
    return session


def test_context_compactor_under_threshold_makes_no_call(fake_llm: FakeLLM):
    # Short session below 30,000 chars
    session = _create_session_with_turns(TaskAgent, num_turns=2, char_multiplier=100)
    assert context_size_chars(session) < TaskAgent.compaction_threshold_chars

    logger = SessionLogger(TaskAgent.name, session.session_id)
    maybe_compact(session, 1, logger)

    assert len(fake_llm.calls_for("Compactor")) == 0


def test_context_compactor_disabled_makes_no_call(fake_llm: FakeLLM):
    agent_disabled = TaskAgent.model_copy(update={"enable_context_compaction": False})
    session = _create_session_with_turns(agent_disabled, num_turns=6, char_multiplier=8000)
    assert context_size_chars(session) > 30000

    logger = SessionLogger(agent_disabled.name, session.session_id)
    maybe_compact(session, 1, logger)

    assert len(fake_llm.calls_for("Compactor")) == 0


def test_context_compactor_over_threshold_compacts_older_history(fake_llm: FakeLLM):
    fake_llm.script("Compactor", raw("ZUSAMMENFASSUNG_DER_RUNDEN"))

    # 6 turns, each with assistant + tool. keep_recent_rounds = 3.
    session = _create_session_with_turns(TaskAgent, num_turns=6, char_multiplier=6000)
    orig_head_system = session.messages[0].content
    orig_head_user = session.messages[1].content
    # The last 3 rounds are rounds 3, 4, 5 (6 messages)
    expected_recent_tail = session.messages[-6:]

    logger = SessionLogger(TaskAgent.name, session.session_id)
    maybe_compact(session, 1, logger)

    calls = fake_llm.calls_for("Compactor")
    assert len(calls) == 1
    assert calls[0].model == str(TaskAgent.compaction_model)

    # Check resulting message structure:
    # 0: original system prompt
    # 1: original first user message
    # 2: compaction summary message
    # 3..: last 3 rounds
    assert session.messages[0].content == orig_head_system
    assert session.messages[1].content == orig_head_user
    assert session.messages[2].role == MessageRole.USER
    assert "ZUSAMMENFASSUNG_DER_RUNDEN" in session.messages[2].content
    assert session.messages[3:] == expected_recent_tail

    # Check no orphaned tool messages (every tool message preceded by matching assistant tool call)
    for idx, msg in enumerate(session.messages):
        if msg.role == MessageRole.TOOL:
            prev = session.messages[idx - 1]
            assert prev.role in (MessageRole.ASSISTANT, MessageRole.TOOL)


def test_context_compactor_exception_leaves_session_intact(fake_llm: FakeLLM):
    fake_llm.script("Compactor", RuntimeError("Compaction model unavailable"))

    session = _create_session_with_turns(TaskAgent, num_turns=6, char_multiplier=6000)
    orig_messages = list(session.messages)

    logger = SessionLogger(TaskAgent.name, session.session_id)
    maybe_compact(session, 1, logger)

    # Session messages must be completely unchanged
    assert session.messages == orig_messages


def test_context_compactor_empty_summary_leaves_session_intact(fake_llm: FakeLLM):
    fake_llm.script("Compactor", raw(""))

    session = _create_session_with_turns(TaskAgent, num_turns=6, char_multiplier=6000)
    orig_messages = list(session.messages)

    logger = SessionLogger(TaskAgent.name, session.session_id)
    maybe_compact(session, 1, logger)

    assert session.messages == orig_messages
