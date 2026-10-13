# src/agentic/engine/runner.py
import contextvars
import json
import time
import litellm
from litellm.utils import supports_tool_choice
from typing import Any, Callable

from src.schemas.llm_models import LLMModels, get_fallback_models
from src.schemas.status import AgentStatus
from src.core.logging_config import logger
from src.agentic.engine.api_errors import (
    FAILOVER_STATUS,
    RETRY_STATUS,
    describe_api_failure,
    short_reason,
)
from src.agentic.engine.session_log import SessionLogger
from src.agentic.engine.compaction import maybe_compact
from src.agentic.engine.response import strip_json_fence
from src.agentic.engine.guards import (
    HALLUCINATED_MUTATION_ERROR,
    SKIPPED_REQUIRED_TOOL_ERROR,
    check_hallucinated_mutation,
    check_skipped_required_tool,
)

from src.schemas.agent_schema import (
    WikiAgent,
    AgentSession,
    LLMCall,
    SessionMessage,
    MessageRole,
    ToolCall,
)

# Upper bound for a single LLM request. Without it a hung connection blocks a whole turn
# for as long as the provider keeps the socket open (observed: 86s for a 2.9 KB prompt
# that then failed anyway), and with a fallback chain behind it that time multiplies.
REQUEST_TIMEOUT_S = 20.0

# A transient server-side error is retried on the SAME model before moving on: every
# model we use sits behind the same provider (see llm_models.py), so a sibling model
# inherits the same outage instead of escaping it. Quota errors are the exception -
# those are per model, so they fail over immediately.
RETRYABLE_ERRORS = (
    litellm.InternalServerError,
    litellm.ServiceUnavailableError,
    litellm.APIConnectionError,
    litellm.Timeout,
)
ATTEMPTS_PER_MODEL = 3
RETRY_BACKOFF_S = (1.0, 3.0)

# Ceiling for ONE logical LLM call including every retry and failover. Per-attempt
# timeouts alone do not bound this: attempts times candidates would still add up to
# minutes on a bad provider minute. Once the budget is spent no further attempt is
# started, and the last attempt is given only the time that is left.
CALL_BUDGET_S = 45.0


def _completion_with_failover(
    completion_kwargs: dict,
    candidates: list[LLMModels],
    agent_name: str,
) -> tuple[Any, LLMModels]:
    """Performs ONE LLM call, with our own retry and failover instead of litellm's
    `fallbacks` parameter. Returns (response, model that actually answered).

    litellm walks its fallback chain once per error and treats every error the same way.
    That is the wrong shape for our model list: a transient 500 is best retried on the
    same model after a short pause, a quota error is best handed to the next model, and a
    hard error (bad request, auth) is not worth sending anywhere. Each attempt is bounded
    by REQUEST_TIMEOUT_S, so a stalled connection costs seconds instead of minutes.

    Raises the last error encountered if no candidate produced a response.
    """
    wants_tool_choice = "tool_choice" in completion_kwargs
    last_error: Exception | None = None
    deadline = time.monotonic() + CALL_BUDGET_S

    for position, model in enumerate(candidates):
        kwargs = dict(completion_kwargs, model=model)
        if wants_tool_choice and not supports_tool_choice(model=str(model)):
            # The Gemma models reject the parameter outright. Previously it was checked
            # only against the primary model while litellm silently forwarded it to the
            # fallbacks, so every fallback of a tool-call round failed before being sent.
            kwargs.pop("tool_choice")

        if position > 0 and last_error is not None:
            # Name the reason for the switch: a rate limit fails over without ever going
            # through the retry message, so this is the only place the user would see it.
            emit_status(
                FAILOVER_STATUS.format(
                    reason=short_reason(last_error), model=str(model).split("/")[-1],
                ),
                STATUS_WARNING,
            )

        for attempt in range(ATTEMPTS_PER_MODEL):
            remaining = deadline - time.monotonic()
            if remaining <= 0 and last_error is not None:
                logger.warning(f"[{agent_name}] Retry budget of {CALL_BUDGET_S}s spent, giving up.")
                raise last_error
            try:
                return litellm.completion(**kwargs, timeout=min(REQUEST_TIMEOUT_S, max(remaining, 1.0))), model
            except litellm.RateLimitError as e:
                # Quota is counted per model - retrying this one would only wait out the
                # same limit, so hand over to the next candidate right away.
                last_error = e
                logger.warning(f"[{agent_name}] Rate limit on {model}, failing over.")
                break
            except RETRYABLE_ERRORS as e:
                last_error = e
                if attempt == ATTEMPTS_PER_MODEL - 1:
                    logger.warning(f"[{agent_name}] {type(e).__name__} on {model} persisted, failing over.")
                    break
                backoff = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
                # The user is staring at a spinner at this point - say what is going on,
                # otherwise a provider outage is indistinguishable from a hang.
                emit_status(
                    RETRY_STATUS.format(
                        reason=short_reason(e), attempt=attempt + 1, total=ATTEMPTS_PER_MODEL,
                    ),
                    STATUS_WARNING,
                )
                logger.warning(
                    f"[{agent_name}] {type(e).__name__} on {model} "
                    f"(attempt {attempt + 1}/{ATTEMPTS_PER_MODEL}), retrying in {backoff}s."
                )
                time.sleep(backoff)
            except Exception:
                # Not transient (bad request, auth, context length, ...): another model
                # would fail the same way, so fail fast instead of burning the chain.
                raise

    raise last_error if last_error is not None else RuntimeError("No model candidates available.")


FORCE_FINAL_ANSWER_INSTRUCTION = (
    "You have almost reached the iteration limit for tool calls. From now on no tools are "
    "available to you. Answer NOW directly in the required JSON format, based solely on what "
    "you have researched so far. Do not call any more tools."
)


_strip_json_fence = strip_json_fence

# Status levels a consumer may render differently. "warning" marks a degraded but still
# running turn (a provider retry or failover), so the UI can show it as more than just
# another progress line.
STATUS_INFO = "info"
STATUS_WARNING = "warning"

_status_callback_var: contextvars.ContextVar[Callable[[str, str], None] | None] = contextvars.ContextVar(
    "_status_callback_var", default=None
)


def emit_status(message: str, level: str = STATUS_INFO) -> None:
    cb = _status_callback_var.get()
    if cb:
        try:
            cb(message, level)
        except Exception:
            pass


def _describe_tool_call(agent_name: str, tool_name: str, arguments: dict) -> str:
    if tool_name == "ask_librarian":
        return "Librarian is researching the vault…"
    if tool_name == "load_files":
        paths = arguments.get("paths", [])
        if paths:
            names = [p.split("/")[-1] for p in paths[:2]]
            suffix = f" (+{len(paths)-2})" if len(paths) > 2 else ""
            return f"Reading note: {', '.join(names)}{suffix}…"
        return "Reading vault notes…"
    if tool_name == "web_search":
        q = arguments.get("query", "").strip()
        if q:
            short_q = q[:35] + "…" if len(q) > 35 else q
            return f"Web search: \u201c{short_q}\u201d…"
        return "Web search running…"
    if tool_name == "deep_reasoning":
        return "Deep reasoning is analyzing…"
    if tool_name == "create_file":
        p = arguments.get("path", "").split("/")[-1]
        return f"Creating file \u201c{p}\u201d…" if p else "Creating file…"
    if tool_name == "edit_file":
        p = arguments.get("path", "").split("/")[-1]
        return f"Editing file \u201c{p}\u201d…" if p else "Editing file…"
    if tool_name == "move_file":
        p = (arguments.get("new_path") or arguments.get("old_path", "")).split("/")[-1]
        return f"Moving file \u201c{p}\u201d…" if p else "Moving file…"
    if tool_name == "delete_file":
        p = arguments.get("path", "").split("/")[-1]
        return f"Deleting file \u201c{p}\u201d…" if p else "Deleting file…"
    if tool_name == "create_directory":
        p = arguments.get("path", "")
        return f"Creating folder \u201c{p}\u201d…" if p else "Creating folder…"
    if tool_name == "directory_summaries":
        return "Librarian is scanning folder overviews…"
    if tool_name == "file_summaries":
        return "Librarian is checking note summaries…"
    if tool_name == "files":
        paths = arguments.get("paths", [])
        if paths:
            names = [p.split("/")[-1] for p in paths[:2]]
            return f"Librarian is reading \u201c{', '.join(names)}\u201d…"
        return "Librarian is reading full-text notes…"
    if tool_name == "start_background_task":
        return "Starting background task…"
    if tool_name == "check_task_status":
        return "Checking background task status…"
    return f"{agent_name}: running {tool_name}…"


def _run_turn(
    session: AgentSession,
    model_override: LLMModels | None = None,
    on_status: Callable[[str, str], None] | None = None,
    rollback_to: int | None = None,
) -> None:
    """Executes ONE turn of an AgentSession: starting from the current conversation
    history (session.messages), possibly several ReAct rounds with tool calls,
    followed by the final structured response (with a retry on parse errors). Mutates
    the given session (messages, history, log_path) and returns nothing - a turn
    corresponds either to the single pass of a one-shot task agent or to a single user
    message within a longer-running chat session.

    The context sent on every LLM call is assembled exclusively from the session itself
    (session.build_messages()) - the session is therefore the sole source of truth for
    the conversation history, including all tool calls and their results. The entire
    session (across all turns) is written to a single log file (see SessionLogger).
    """
    token = None
    if on_status is not None:
        token = _status_callback_var.set(on_status)

    try:
        agent = session.agent
        use_model = model_override or agent.default_model

        tools_by_name = {tool.name: tool for tool in agent.tools}
        tool_schemas = [tool.to_openai_schema() for tool in agent.tools]

        session_logger = SessionLogger(agent_name=agent.name, session_id=session.session_id, existing_path=session.log_path)
        session.log_path = session_logger.filepath

        tool_steps = 0
        parse_attempts = 0
        force_final_answer = False
        # Where this turn began, so an attempt that dies before doing anything can be
        # rolled back instead of leaving a dangling user message in the session. Callers
        # that append the user message themselves (continue_chat_session) pass the index
        # from BEFORE that message, so a rolled-back turn takes it with it.
        messages_at_turn_start = len(session.messages) if rollback_to is None else rollback_to

        while True:
            step = len(session.history) + 1
            messages = session.build_messages()
            chars_in = sum(len(m.get("content") or "") for m in messages)

            if tool_steps == 0:
                if agent.name == "Chat":
                    emit_status("Chat assistant is thinking…")
                elif agent.name == "Librarian":
                    emit_status("Librarian recherchiert im Vault…")
                else:
                    emit_status(f"{agent.name} is thinking…")

            offer_tools = bool(tool_schemas) and not force_final_answer
            fallbacks = get_fallback_models(use_model, offer_tools=offer_tools)
            completion_kwargs = dict(
                model=use_model,
                messages=messages,
                # Retry, failover and the per-attempt timeout are handled by
                # _completion_with_failover, which needs litellm to report the raw error
                # instead of silently retrying itself.
                num_retries=0,
            )
            if getattr(agent, "temperature", None) is not None:
                completion_kwargs["temperature"] = agent.temperature
            if offer_tools:
                # Function calling and an enforced response_format do not work together
                # on most providers: as long as tools are available, the system prompt
                # alone (build_response_format_prompt) governs the expected JSON format
                # of the final response.
                completion_kwargs["tools"] = tool_schemas
                # Prevents the model from skipping the very first round and returning a
                # (possibly entirely hallucinated) final answer without ever having used a
                # tool - this happens in practice even with otherwise reliable models.
                # The supports_tool_choice() check is needed because Gemma models do not
                # support it and the request would otherwise fail; _completion_with_failover
                # repeats the check for each fallback candidate it tries.
                if tool_steps == 0 and agent.require_tool_call_first_round and supports_tool_choice(model=str(use_model)):
                    completion_kwargs["tool_choice"] = "required"
            else:
                completion_kwargs["response_format"] = agent.response_type

            try:
                response, use_model = _completion_with_failover(
                    completion_kwargs,
                    candidates=[use_model, *fallbacks],
                    agent_name=agent.name,
                )
            except Exception as api_e:
                session_logger.log_api_error(step, model=str(use_model), messages=messages, error=str(api_e))
                call_record = LLMCall(
                    agent_name=agent.name,
                    status=AgentStatus.ERROR,
                    input_data=session.first_input,
                    error_message=f"API error: {api_e}",
                    user_message=describe_api_failure(api_e),
                    chars_in=chars_in,
                    chars_out=0,
                )
                session.history.append(call_record)
                logger.error(call_record.get_short_log())
                # Nothing was executed yet, so the half-finished turn (the user message
                # and any rejected parse attempts) is worthless context that the next
                # call would have to pay for again - and it would leave the history
                # ending on a user message with no assistant reply. Once tools HAVE run
                # the rounds are kept: they may have mutated the vault, and that record
                # has to stay in the session.
                if tool_steps == 0:
                    del session.messages[messages_at_turn_start:]
                break

            resp_model = getattr(response, "model", None)
            if resp_model:
                for m in LLMModels:
                    if m.value == resp_model or m.value.split("/")[-1] == resp_model:
                        use_model = m
                        break

            message = response.choices[0].message
            usage = getattr(response, "usage", None)
            raw_content = (message.content or "").strip()
            chars_out = len(raw_content)
            tokens_in = getattr(usage, "prompt_tokens", chars_in) if usage else chars_in
            tokens_out = getattr(usage, "completion_tokens", chars_out) if usage else chars_out

            requested_tool_calls = getattr(message, "tool_calls", None) or []

            if requested_tool_calls:
                tool_steps += 1
                executed: list[ToolCall] = []
                for tc in requested_tool_calls:
                    try:
                        arguments = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    executed.append(ToolCall(id=tc.id, tool_name=tc.function.name, arguments=arguments))

                session.messages.append(SessionMessage(
                    role=MessageRole.ASSISTANT,
                    content=message.content,
                    tool_calls=executed,
                ))

                for tool_call in executed:
                    emit_status(_describe_tool_call(agent.name, tool_call.tool_name, tool_call.arguments))
                    tool = tools_by_name.get(tool_call.tool_name)
                    tool_call.result = (
                        tool.call(tool_call.arguments) if tool
                        else f"Error: unknown tool '{tool_call.tool_name}'."
                    )
                    session.messages.append(SessionMessage(
                        role=MessageRole.TOOL,
                        content=tool_call.result,
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.tool_name,
                    ))

                call_record = LLMCall(
                    agent_name=agent.name,
                    status=AgentStatus.TOOL_CALL,
                    input_data=session.first_input,
                    tool_calls=executed,
                    chars_in=chars_in,
                    chars_out=chars_out,
                )
                session.history.append(call_record)
                session_logger.log_step(
                    step, call_record, messages, str(use_model),
                    message.content or "(no text, tool calls only)",
                    tokens_in, tokens_out,
                )
                logger.info(call_record.get_short_log())

                # After a completed round (a clean cut point: no tool call without its
                # result), optionally compact the older history to limit the number of
                # tokens sent per round in long sessions (see compaction.py).
                maybe_compact(session, step, session_logger)

                if agent.name == "Chat":
                    emit_status("Chat assistant is composing a reply…")
                elif agent.name == "Librarian":
                    emit_status("Librarian is composing an answer…")

                # One round before the actual limit: stop offering tool calls and ask the
                # model explicitly for its final answer, rather than ending the session at
                # harten Limit einfach ergebnislos abzubrechen.
                if not force_final_answer and tool_steps >= agent.max_tool_iterations - 1:
                    force_final_answer = True
                    session.messages.append(SessionMessage(role=MessageRole.USER, content=FORCE_FINAL_ANSWER_INSTRUCTION))
                    logger.info(
                        f"[{agent.name}] Iterationslimit fast erreicht ({tool_steps}/{agent.max_tool_iterations}) "
                        f"- forcing a final answer with no further tool calls."
                    )
                continue

            # No further tool call requested -> this should be the final, structured response.
            parse_result = agent.parse_response(_strip_json_fence(raw_content))
            session.messages.append(SessionMessage(role=MessageRole.ASSISTANT, content=raw_content))
            # The model skipped the required "use at least one tool first" step and
            # returned a (possibly entirely hallucinated) final answer straight away -
            # despite valid JSON this must NOT count as success; treat it as a parse error.
            skipped_required_tool = check_skipped_required_tool(agent, tool_steps)

            # Check whether the agent claimed or announced a file modification in its text
            # without ever having called a corresponding tool (e.g. create_file, edit_file).
            hallucinated_mutation = check_hallucinated_mutation(agent, parse_result, tool_steps)

            if parse_result.status == AgentStatus.SUCCESS and not skipped_required_tool and not hallucinated_mutation:
                call_record = LLMCall(
                    agent_name=agent.name,
                    status=AgentStatus.SUCCESS,
                    input_data=session.first_input,
                    output_data=parse_result.parsed_data,
                    chars_in=chars_in,
                    chars_out=chars_out,
                )
                session.history.append(call_record)
                session_logger.log_step(step, call_record, messages, str(use_model), raw_content, tokens_in, tokens_out)
                logger.info(call_record.get_short_log())
                logger.debug(call_record.get_detailed_log())
                break

            if skipped_required_tool:
                error_report = SKIPPED_REQUIRED_TOOL_ERROR
            elif hallucinated_mutation:
                error_report = HALLUCINATED_MUTATION_ERROR
            else:
                error_report = parse_result.error_report

            parse_attempts += 1
            call_record = LLMCall(
                agent_name=agent.name,
                status=AgentStatus.ERROR,
                input_data=session.first_input,
                error_message=error_report,
                chars_in=chars_in,
                chars_out=chars_out,
            )
            session.history.append(call_record)
            session_logger.log_step(step, call_record, messages, str(use_model), raw_content, tokens_in, tokens_out)
            logger.warning(call_record.get_short_log())
            logger.debug(call_record.get_detailed_log())

            if parse_attempts > agent.max_retries:
                break

            session.messages.append(SessionMessage(role=MessageRole.USER, content=error_report))

        session_logger.log_turn_end(session)
    finally:
        if token is not None:
            _status_callback_var.reset(token)


def run_agent_session(
    agent: WikiAgent,
    raw_input: Any,
    model_override: LLMModels = None,
    on_status: Callable[[str, str], None] | None = None,
) -> AgentSession:
    """Runs a complete one-shot task session (e.g. Summarizer, FolderSummarizer,
    Librarian): one input in, one structured response out, with possibly several ReAct
    tool rounds in between."""
    valid_input = agent.validate_input(raw_input)
    session = AgentSession(agent=agent, first_input=valid_input)
    session.start(valid_input)
    _run_turn(session, model_override, on_status=on_status)
    return session


def start_chat_session(
    agent: WikiAgent,
    message: str,
    model_override: LLMModels = None,
    context: str | None = None,
    on_status: Callable[[str, str], None] | None = None,
) -> AgentSession:
    """Starts a new chat session with the first user message. The agent must have an
    input_type with a 'message' field (see ChatInput). 'context', if given, is placed
    additionally into the system prompt (e.g. the current ai_map) without polluting the
    visible first chat message."""
    valid_input = agent.validate_input({"message": message})
    session = AgentSession(agent=agent, first_input=valid_input)
    session.start_chat(message, context=context)
    _run_turn(session, model_override, on_status=on_status)
    return session


def continue_chat_session(
    session: AgentSession,
    message: str,
    model_override: LLMModels = None,
    on_status: Callable[[str, str], None] | None = None,
) -> AgentSession:
    """Appends another user message to an already running chat session and lets the agent
    respond to it (again possibly with tool calls). The entire history so far is
    preserved - same session_id, same log file."""
    turn_start = len(session.messages)
    session.add_user_message(message)
    _run_turn(session, model_override, on_status=on_status, rollback_to=turn_start)
    return session
