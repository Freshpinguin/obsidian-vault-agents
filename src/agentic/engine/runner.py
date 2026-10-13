# src/agentic/engine/runner.py
import contextvars
import json
import litellm
from litellm.utils import supports_tool_choice
from typing import Any, Callable

from src.schemas.llm_models import FALLBACK_MAP, LLMModels
from src.schemas.status import AgentStatus
from src.core.logging_config import logger
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

FORCE_FINAL_ANSWER_INSTRUCTION = (
    "Du hast das Iterationslimit für Werkzeug-Aufrufe fast erreicht. Ab jetzt stehen dir keine Werkzeuge "
    "mehr zur Verfügung. Antworte JETZT direkt im geforderten JSON-Format, ausschließlich gestützt auf das, "
    "was du bisher recherchiert hast. Rufe kein Werkzeug mehr auf."
)


_strip_json_fence = strip_json_fence

_status_callback_var: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar(
    "_status_callback_var", default=None
)


def emit_status(message: str) -> None:
    cb = _status_callback_var.get()
    if cb:
        try:
            cb(message)
        except Exception:
            pass


def _describe_tool_call(agent_name: str, tool_name: str, arguments: dict) -> str:
    if tool_name == "ask_librarian":
        return "Librarian recherchiert im Vault…"
    if tool_name == "load_files":
        paths = arguments.get("paths", [])
        if paths:
            names = [p.split("/")[-1] for p in paths[:2]]
            suffix = f" (+{len(paths)-2})" if len(paths) > 2 else ""
            return f"Liest Notiz: {', '.join(names)}{suffix}…"
        return "Liest Vault-Notizen…"
    if tool_name == "web_search":
        q = arguments.get("query", "").strip()
        if q:
            short_q = q[:35] + "…" if len(q) > 35 else q
            return f"Websuche: „{short_q}“…"
        return "Websuche läuft…"
    if tool_name == "deep_reasoning":
        return "Deep Reasoning analysiert…"
    if tool_name == "create_file":
        p = arguments.get("path", "").split("/")[-1]
        return f"Erstellt Datei „{p}“…" if p else "Erstellt Datei…"
    if tool_name == "edit_file":
        p = arguments.get("path", "").split("/")[-1]
        return f"Bearbeitet Datei „{p}“…" if p else "Bearbeitet Datei…"
    if tool_name == "move_file":
        p = (arguments.get("new_path") or arguments.get("old_path", "")).split("/")[-1]
        return f"Verschiebt Datei „{p}“…" if p else "Verschiebt Datei…"
    if tool_name == "delete_file":
        p = arguments.get("path", "").split("/")[-1]
        return f"Löscht Datei „{p}“…" if p else "Löscht Datei…"
    if tool_name == "create_directory":
        p = arguments.get("path", "")
        return f"Erstellt Ordner „{p}“…" if p else "Erstellt Ordner…"
    if tool_name == "directory_summaries":
        return "Librarian scannt Ordner-Übersichten…"
    if tool_name == "file_summaries":
        return "Librarian prüft Notiz-Zusammenfassungen…"
    if tool_name == "files":
        paths = arguments.get("paths", [])
        if paths:
            names = [p.split("/")[-1] for p in paths[:2]]
            return f"Librarian liest „{', '.join(names)}“…"
        return "Librarian liest Volltext-Notizen…"
    if tool_name == "start_background_task":
        return "Startet Hintergrundaufgabe…"
    if tool_name == "check_task_status":
        return "Prüft Status der Hintergrundaufgabe…"
    return f"{agent_name}: Führt {tool_name} aus…"


def _run_turn(
    session: AgentSession,
    model_override: LLMModels | None = None,
    on_status: Callable[[str], None] | None = None,
) -> None:
    """Führt EINEN Turn einer AgentSession aus: ausgehend vom aktuellen Gesprächsverlauf
    (session.messages) ggf. mehrere ReAct-Runden mit Tool-Aufrufen, gefolgt von der
    finalen strukturierten Antwort (mit Retry bei Parse-Fehlern). Mutiert die übergebene
    Session (messages, history, log_path) und gibt nichts zurück – ein Turn entspricht
    dabei entweder der einzigen Verarbeitung eines Ein-Schritt-Task-Agenten oder einer
    einzelnen Nutzer-Nachricht innerhalb einer länger laufenden Chat-Session.

    Der bei jedem LLM-Aufruf gesendete Kontext wird ausschließlich aus der Session selbst
    zusammengesetzt (session.build_messages()) – die Session ist damit die alleinige
    Quelle der Wahrheit für den Gesprächsverlauf, inklusive aller Tool-Aufrufe und deren
    Ergebnisse. Die gesamte Session (über alle Turns hinweg) landet in einer einzigen
    Logdatei (siehe SessionLogger).
    """
    token = None
    if on_status is not None:
        token = _status_callback_var.set(on_status)

    try:
        agent = session.agent
        use_model = model_override or agent.default_model
        active_fallbacks = FALLBACK_MAP.get(use_model, [])

        tools_by_name = {tool.name: tool for tool in agent.tools}
        tool_schemas = [tool.to_openai_schema() for tool in agent.tools]

        session_logger = SessionLogger(agent_name=agent.name, session_id=session.session_id, existing_path=session.log_path)
        session.log_path = session_logger.filepath

        tool_steps = 0
        parse_attempts = 0
        force_final_answer = False

        while True:
            step = len(session.history) + 1
            messages = session.build_messages()
            chars_in = sum(len(m.get("content") or "") for m in messages)

            if tool_steps == 0:
                if agent.name == "Chat":
                    emit_status("Chat-Assistent überlegt…")
                elif agent.name == "Librarian":
                    emit_status("Librarian recherchiert im Vault…")
                else:
                    emit_status(f"{agent.name} überlegt…")

            offer_tools = bool(tool_schemas) and not force_final_answer
            completion_kwargs = dict(model=use_model, messages=messages, fallbacks=active_fallbacks)
            if getattr(agent, "temperature", None) is not None:
                completion_kwargs["temperature"] = agent.temperature
            if offer_tools:
                # Function-Calling und erzwungenes response_format vertragen sich bei den
                # meisten Providern nicht gleichzeitig: solange Tools zur Verfügung stehen,
                # steuert allein der System-Prompt (build_response_format_prompt) das
                # erwartete JSON-Format der finalen Antwort.
                completion_kwargs["tools"] = tool_schemas
                # Verhindert, dass das Modell die allererste Runde überspringt und direkt eine
                # (ggf. komplett halluzinierte) finale Antwort liefert, ohne je ein Tool genutzt
                # zu haben - passiert in der Praxis auch bei sonst zuverlässigen Modellen.
                # supports_tool_choice()-Check, da Gemma-Modelle (Fallback-Kandidaten) das nicht
                # unterstützen und der Request sonst fehlschlagen würde.
                if tool_steps == 0 and agent.require_tool_call_first_round and supports_tool_choice(model=str(use_model)):
                    completion_kwargs["tool_choice"] = "required"
            else:
                completion_kwargs["response_format"] = agent.response_type

            try:
                response = litellm.completion(**completion_kwargs)
            except Exception as api_e:
                session_logger.log_api_error(step, model=str(use_model), messages=messages, error=str(api_e))
                call_record = LLMCall(
                    agent_name=agent.name,
                    status=AgentStatus.ERROR,
                    input_data=session.first_input,
                    error_message=f"API Fehler: {api_e}",
                    chars_in=chars_in,
                    chars_out=0,
                )
                session.history.append(call_record)
                logger.error(call_record.get_short_log())
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
                        else f"Fehler: Unbekanntes Tool '{tool_call.tool_name}'."
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
                    message.content or "(kein Text, nur Tool-Aufrufe)",
                    tokens_in, tokens_out,
                )
                logger.info(call_record.get_short_log())

                # Nach einer abgeschlossenen Runde (sauberer Schnittpunkt: kein Tool-Call ohne
                # zugehöriges Ergebnis) ggf. den älteren Verlauf verdichten, um die pro Runde
                # gesendete Tokenmenge bei langen Sessions zu begrenzen (siehe context_compactor.py).
                maybe_compact(session, step, session_logger)

                if agent.name == "Chat":
                    emit_status("Chat-Assistent formuliert Antwort…")
                elif agent.name == "Librarian":
                    emit_status("Librarian formuliert Antwort…")

                # Eine Runde vor dem eigentlichen Limit: keine weiteren Tool-Aufrufe mehr anbieten
                # und das Modell explizit zur finalen Antwort auffordern, statt die Session beim
                # harten Limit einfach ergebnislos abzubrechen.
                if not force_final_answer and tool_steps >= agent.max_tool_iterations - 1:
                    force_final_answer = True
                    session.messages.append(SessionMessage(role=MessageRole.USER, content=FORCE_FINAL_ANSWER_INSTRUCTION))
                    logger.info(
                        f"[{agent.name}] Iterationslimit fast erreicht ({tool_steps}/{agent.max_tool_iterations}) "
                        f"– erzwinge finale Antwort ohne weitere Tool-Aufrufe."
                    )
                continue

            # Kein Tool-Aufruf mehr angefordert -> das sollte die finale, strukturierte Antwort sein.
            parse_result = agent.parse_response(_strip_json_fence(raw_content))
            session.messages.append(SessionMessage(role=MessageRole.ASSISTANT, content=raw_content))
            # Modell hat den geforderten "erst mindestens ein Tool nutzen"-Schritt übersprungen
            # und direkt eine (evtl. komplett halluzinierte) finale Antwort geliefert - trotz
            # gültigem JSON NICHT als Erfolg werten, sondern wie einen Parse-Fehler behandeln.
            skipped_required_tool = check_skipped_required_tool(agent, tool_steps)

            # Prüfen, ob der Agent eine Dateimodifikation im Text behauptet/angekündigt hat,
            # ohne je ein entsprechendes Werkzeug (z.B. create_file, edit_file) aufgerufen zu haben.
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
    on_status: Callable[[str], None] | None = None,
) -> AgentSession:
    """Führt eine vollständige Ein-Schritt-Task-Session aus (z.B. Summarizer,
    FolderSummarizer, Librarian): eine Eingabe rein, eine strukturierte Antwort raus,
    dazwischen ggf. mehrere ReAct-Tool-Runden."""
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
    on_status: Callable[[str], None] | None = None,
) -> AgentSession:
    """Startet eine neue Chat-Session mit der ersten Nutzer-Nachricht. Der Agent muss
    ein input_type mit einem Feld 'message' haben (siehe ChatInput). 'context' landet,
    falls angegeben, zusätzlich im System-Prompt (z.B. die aktuelle ai_map), ohne die
    sichtbare erste Chat-Nachricht zu verunreinigen."""
    valid_input = agent.validate_input({"message": message})
    session = AgentSession(agent=agent, first_input=valid_input)
    session.start_chat(message, context=context)
    _run_turn(session, model_override, on_status=on_status)
    return session


def continue_chat_session(
    session: AgentSession,
    message: str,
    model_override: LLMModels = None,
    on_status: Callable[[str], None] | None = None,
) -> AgentSession:
    """Hängt eine weitere Nutzer-Nachricht an eine bereits laufende Chat-Session an und
    lässt den Agenten (erneut ggf. mit Tool-Aufrufen) darauf antworten. Die komplette
    bisherige Historie bleibt erhalten – gleiche session_id, gleiche Logdatei."""
    session.add_user_message(message)
    _run_turn(session, model_override, on_status=on_status)
    return session
