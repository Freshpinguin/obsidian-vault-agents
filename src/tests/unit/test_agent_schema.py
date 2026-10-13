from pydantic import BaseModel, Field
import pytest

from src.schemas.agent_schema import (
    AgentSession,
    AgentStatus,
    LLMCall,
    MessageRole,
    SessionMessage,
    ToolCall,
    WikiAgent,
)
from src.schemas.tool_schema import WikiTool


class SimpleInput(BaseModel):
    message: str


class SimpleOutput(BaseModel):
    reply: str = Field(description="Antwort an den Nutzer")
    score: int = Field(description="Bewertung von 1 bis 10")


class DummyArgs(BaseModel):
    x: str


def test_session_message_to_openai_roles():
    # User
    msg_user = SessionMessage(role=MessageRole.USER, content="Hello")
    assert msg_user.to_openai() == {"role": "user", "content": "Hello"}

    # System
    msg_sys = SessionMessage(role=MessageRole.SYSTEM, content="System prompt")
    assert msg_sys.to_openai() == {"role": "system", "content": "System prompt"}

    # Assistant without tools
    msg_asst = SessionMessage(role=MessageRole.ASSISTANT, content="Hi there")
    assert msg_asst.to_openai() == {"role": "assistant", "content": "Hi there"}

    # Tool role
    msg_tool = SessionMessage(role=MessageRole.TOOL, content="Tool output", tool_call_id="call_123")
    assert msg_tool.to_openai() == {"role": "tool", "content": "Tool output", "tool_call_id": "call_123"}

    # Assistant with tool calls (ensure_ascii=False for unicode)
    tc = ToolCall(id="tc_1", tool_name="create_file", arguments={"path": "Kulturen/Ära.md"})
    msg_asst_tools = SessionMessage(role=MessageRole.ASSISTANT, tool_calls=[tc])
    openai_asst = msg_asst_tools.to_openai()
    assert openai_asst["role"] == "assistant"
    assert len(openai_asst["tool_calls"]) == 1
    call_json = openai_asst["tool_calls"][0]["function"]["arguments"]
    assert "Ära.md" in call_json  # ensure_ascii=False preserves Umlauts


def test_wiki_agent_parse_response():
    agent = WikiAgent(
        name="TestAgent",
        system_prompt="Test",
        input_type=SimpleInput,
        response_type=SimpleOutput,
    )

    # Valid response
    valid_json = '{"reply": "Alles gut", "score": 9}'
    parse_ok = agent.parse_response(valid_json)
    assert parse_ok.status == AgentStatus.SUCCESS
    assert parse_ok.parsed_data.reply == "Alles gut"
    assert parse_ok.parsed_data.score == 9

    # Invalid response (missing score, invalid type)
    invalid_json = '{"reply": "Missing score"}'
    parse_err = agent.parse_response(invalid_json)
    assert parse_err.status == AgentStatus.ERROR
    assert "score" in parse_err.error_report
    assert "Missing score" in parse_err.error_report


def test_build_response_format_prompt():
    agent_no_tools = WikiAgent(
        name="AgentNoTools",
        system_prompt="Prompt",
        input_type=SimpleInput,
        response_type=SimpleOutput,
    )
    prompt_no_tools = agent_no_tools.build_response_format_prompt()
    assert "Antworte ausschließlich mit einem einzigen validen JSON-Objekt" in prompt_no_tools
    assert '"reply": "<Antwort an den Nutzer>"' in prompt_no_tools
    assert '"score": "<Bewertung von 1 bis 10>"' in prompt_no_tools

    tool = WikiTool(
        name="dummy_tool",
        description="A dummy tool",
        parameters=DummyArgs,
        func=lambda x: "ok",
    )
    agent_with_tools = WikiAgent(
        name="AgentWithTools",
        system_prompt="Prompt",
        input_type=SimpleInput,
        response_type=SimpleOutput,
        tools=[tool],
    )
    prompt_with_tools = agent_with_tools.build_response_format_prompt()
    assert "## Antwortformat und Werkzeugnutzung" in prompt_with_tools
    assert "Behaupte NIEMALS im Text einer Antwort" in prompt_with_tools


def test_agent_session_start_and_start_chat():
    agent = WikiAgent(
        name="AgentTest",
        system_prompt="SYSTEM_BASE",
        input_type=SimpleInput,
        response_type=SimpleOutput,
    )

    # start() for task agent
    sess_task = AgentSession(agent=agent, first_input=SimpleInput(message="do task"))
    sess_task.start(SimpleInput(message="do task"))
    assert len(sess_task.messages) == 2
    assert sess_task.messages[0].role == MessageRole.SYSTEM
    assert "SYSTEM_BASE" in sess_task.messages[0].content
    assert sess_task.messages[1].role == MessageRole.USER
    assert "Bitte verarbeite folgende Daten" in sess_task.messages[1].content

    # start_chat() with extra context
    sess_chat = AgentSession(agent=agent, first_input=SimpleInput(message="hi"))
    sess_chat.start_chat("hi", context="EXTRA_CONTEXT_MAP")
    assert len(sess_chat.messages) == 2
    # Extra context is inside system message, NOT user message
    assert "EXTRA_CONTEXT_MAP" in sess_chat.messages[0].content
    assert sess_chat.messages[1].content == "hi"


def test_agent_session_is_successful_and_final_result():
    agent = WikiAgent(
        name="AgentTest",
        system_prompt="Prompt",
        input_type=SimpleInput,
        response_type=SimpleOutput,
    )
    session = AgentSession(agent=agent, first_input=SimpleInput(message="test"))

    assert not session.is_successful
    assert session.final_result is None

    # Add error call
    session.history.append(
        LLMCall(
            agent_name=agent.name,
            status=AgentStatus.ERROR,
            input_data=session.first_input,
            error_message="Fail",
        )
    )
    assert not session.is_successful
    assert session.final_result is None

    # Add success call
    session.history.append(
        LLMCall(
            agent_name=agent.name,
            status=AgentStatus.SUCCESS,
            input_data=session.first_input,
            output_data=SimpleOutput(reply="Done", score=10),
        )
    )
    assert session.is_successful
    assert session.final_result.reply == "Done"
    assert session.final_result.score == 10
