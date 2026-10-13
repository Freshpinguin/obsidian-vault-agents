# src/schemas/agent_schema.py
import json
import uuid
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Type, Any
from src.schemas.status import AgentStatus, ParseResult
from src.schemas.llm_models import LLMModels
from src.schemas.tool_schema import WikiTool


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """Ein einzelner Tool-Aufruf innerhalb eines LLM-Turns, inklusive Ergebnis."""
    id: str
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    result: str | None = None


class SessionMessage(BaseModel):
    """A message in the conversation history of an AgentSession. The session consists
    of a list of these messages; the context for every LLM call (the 'messages' for the
    litellm completion) is reassembled from them (see AgentSession.build_messages)."""
    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None

    def to_openai(self) -> dict:
        if self.role == MessageRole.ASSISTANT and self.tool_calls:
            return {
                "role": "assistant",
                "content": self.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.tool_name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                    }
                    for tc in self.tool_calls
                ],
            }
        if self.role == MessageRole.TOOL:
            return {"role": "tool", "tool_call_id": self.tool_call_id, "content": self.content or ""}
        return {"role": self.role.value, "content": self.content or ""}


class WikiAgent(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    system_prompt: str
    input_type: Type[BaseModel]
    response_type: Type[BaseModel]
    default_model:LLMModels =LLMModels.GEMINI_3_5_FLASH_LITE
    temperature: float = Field(default=0.2, description="Sampling temperature for this agent's LLM calls.")
    max_retries: int = Field(default=3, description="Maximum retries on parse errors of the final response.")
    tools: list[WikiTool] = Field(default_factory=list, description="Tools the agent can call via the ReAct loop.")
    max_tool_iterations: int = Field(default=15, description="Maximum number of tool-call rounds (ReAct steps) per session.")
    enable_context_compaction: bool = Field(
        default=False,
        description="Whether the older conversation history is compacted by a cheap LLM when needed, to "
                     "save tokens (see compaction.py). Useful for agents with many ReAct rounds.",
    )
    compaction_model: LLMModels = Field(default=LLMModels.GEMMA_26B, description="Cheap model used for context compaction.")
    compaction_threshold_chars: int = Field(default=30000, description="The number of characters in the current context above which compaction is triggered.")
    compaction_keep_recent_rounds: int = Field(default=3, description="How many of the most recent ReAct rounds are left untouched when compacting.")
    require_tool_call_first_round: bool = Field(
        default=False,
        description="Forces a tool call in the very first round of a turn via tool_choice='required', and "
                     "treats a final response without ANY tool call as invalid (retry instead of success). "
                     "Only useful for agents whose prompt requires them to ALWAYS use at least one tool "
                     "(e.g. TaskAgent: update_plan) - prevents the model from hallucinating a complex task "
                     "as 'done' without ever having done anything.",
    )

    def build_response_format_prompt(self) -> str:
        """Derives the instruction for the expected JSON response format from response_type."""
        lines = [
            f'  "{field_name}": "<{field.description or field_name}>"'
            for field_name, field in self.response_type.model_fields.items()
        ]
        schema_block = "{\n" + ",\n".join(lines) + "\n}"
        if self.tools:
            return (
                "## Response format and tool usage\n"
                "IMPORTANT RULES:\n"
                "1. If tools are required or sensible for the request (e.g. reading, searching, creating, editing or moving files), "
                "you must call the appropriate tools as tool calls FIRST!\n"
                "2. NEVER claim in the text of a response that you have created, changed or read a file "
                "without having actually called the tool for it.\n"
                "3. Only once all required tools have been executed (or, for simple answers/small talk, without tools) "
                "do you give your final answer as a valid JSON object following this schema (no Markdown code block, no text before or after):\n"
                + schema_block
            )
        return (
            "Reply exclusively with a single valid JSON object following exactly this schema, "
            "with no additional text and no Markdown code block:\n" + schema_block
        )

    def validate_input(self, input_data: Any) -> BaseModel:
        if isinstance(input_data, dict):
            return self.input_type.model_validate(input_data)
        elif isinstance(input_data, BaseModel):
            return self.input_type.model_validate(input_data.model_dump())
        raise ValueError(f"[{self.name}] input_data must be a dict or a BaseModel.")

    def parse_response(self, raw_output: str) -> ParseResult:
        """
        Validates the string against the response_type schema.
        On failure, generates a detailed textual report for the LLM.
        """
        try:
            parsed = self.response_type.model_validate_json(raw_output)
            return ParseResult(status=AgentStatus.SUCCESS, parsed_data=parsed)
            
        except ValidationError as e:
            errors = e.errors()
            error_messages = []
            
            for err in errors:
                field_path = " -> ".join([str(loc) for loc in err['loc']])
                msg = err['msg']
                input_val = err.get('input', 'unknown')
                error_messages.append(f"- Field '{field_path}': {msg}. (Your input was: {input_val})")

            report = (
                "The previous response was invalid and did not match the required JSON schema. "
                "You must correct the following errors:\n" + 
                "\n".join(error_messages) +
                "\n\nHere is your faulty raw response for reference:\n" +
                f"```json\n{raw_output}\n```"
            )
            return ParseResult(status=AgentStatus.ERROR, error_report=report)

class LLMCall(BaseModel):
    """A single LLM turn within an AgentSession: either one or more tool calls
    (status=TOOL_CALL), an invalid final response (status=ERROR), or the valid final
    response (status=SUCCESS)."""
    agent_name: str
    status: AgentStatus
    input_data: BaseModel
    output_data: BaseModel | None = None
    error_message: str | None = None
    user_message: str | None = Field(
        default=None,
        description=(
            "Error text meant for the chat UI: one sentence, no stack trace (see "
            "engine/api_errors.py). error_message keeps the technical version for the log."
        ),
    )
    tool_calls: list[ToolCall] = Field(default_factory=list)
    chars_in: int = 0
    chars_out: int = 0

    def get_short_log(self) -> str:
        markers = {
            AgentStatus.SUCCESS: "✅ SUCCESS",
            AgentStatus.ERROR: "❌ ERROR",
            AgentStatus.TOOL_CALL: f"🔧 TOOL_CALL ({', '.join(tc.tool_name for tc in self.tool_calls)})",
        }
        return f"[{self.agent_name}] {markers[self.status]} | In: {self.chars_in} chars | Out: {self.chars_out} chars"

    def get_detailed_log(self) -> str:
        log_lines = [
            f"=== [{self.agent_name}] LLM CALL DETAILED LOG ===",
            f"Status: {self.status.upper()}",
            "--- INPUT ---",
            self.input_data.model_dump_json(indent=2),
        ]
        if self.status == AgentStatus.SUCCESS and self.output_data:
            log_lines.extend(["--- OUTPUT ---", self.output_data.model_dump_json(indent=2)])
        elif self.status == AgentStatus.TOOL_CALL:
            log_lines.append("--- TOOL CALLS ---")
            for tc in self.tool_calls:
                log_lines.append(f"{tc.tool_name}({tc.arguments}) -> {tc.result}")
        else:
            log_lines.extend(["--- ERROR ---", self.error_message or "Unknown error"])
        log_lines.append("=========================================")
        return "\n".join(log_lines)

class AgentSession(BaseModel):
    """A ReAct session: from the first input, through any number of tool calls, to the
    final structured response. 'messages' is the complete conversation history and the
    sole source of the context sent on every LLM call (see build_messages) - nothing is
    carried alongside it. 'history' is the turn-by-turn record (for logging/statistics
    and the final success/result check)."""
    agent: WikiAgent
    first_input: BaseModel
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: datetime = Field(default_factory=datetime.now)
    messages: list[SessionMessage] = Field(default_factory=list)
    history: list[LLMCall] = Field(default_factory=list)
    log_path: str | None = Field(default=None, description="Path of this session's log file (see SessionLogger) - the same file across all turns.")

    def _system_message(self, extra_context: str | None = None) -> SessionMessage:
        system_content = f"{self.agent.system_prompt}\n\n{self.agent.build_response_format_prompt()}"
        if extra_context:
            system_content += f"\n\n{extra_context}"
        return SessionMessage(role=MessageRole.SYSTEM, content=system_content)

    def start(self, valid_input: BaseModel) -> None:
        """Initializes the conversation history of a one-shot task agent with the system
        prompt and the complete input as JSON. Must be called once at the start of the
        session before build_messages() returns anything useful."""
        self.messages.append(self._system_message())
        self.messages.append(SessionMessage(
            role=MessageRole.USER,
            content=f"Please process the following data:\n\n```json\n{valid_input.model_dump_json(indent=2)}\n```",
        ))

    def start_chat(self, first_message: str, context: str | None = None) -> None:
        """Initializes the conversation history of a chat agent: the system prompt
        (optionally extended with additional background context, e.g. the current ai_map,
        so the agent knows it from the outset instead of having to ask for it) plus the
        first user message as plain text (no JSON wrapper as in start()), so the whole
        thing reads like a normal conversation."""
        self.messages.append(self._system_message(context))
        self.messages.append(SessionMessage(role=MessageRole.USER, content=first_message))

    def add_user_message(self, message: str) -> None:
        """Appends another user message to an already running chat session (e.g. a
        follow-up question) without losing the history so far."""
        self.messages.append(SessionMessage(role=MessageRole.USER, content=message))

    def build_messages(self) -> list[dict]:
        """Assembles the complete litellm context from the conversation history so far
        (self.messages). The context for every LLM call therefore arises exclusively from
        the session itself, not from a separate variable."""
        return [m.to_openai() for m in self.messages]

    @property
    def tool_steps(self) -> int:
        return sum(1 for call in self.history if call.status == AgentStatus.TOOL_CALL)

    @property
    def is_successful(self) -> bool:
        return bool(self.history and self.history[-1].status == AgentStatus.SUCCESS)

    @property
    def final_result(self) -> BaseModel | None:
        if self.is_successful:
            return self.history[-1].output_data
        return None