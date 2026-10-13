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
    """Eine Nachricht im Gesprächsverlauf einer AgentSession. Die Session besteht aus
    einer Liste dieser Nachrichten; daraus wird bei jedem LLM-Aufruf der Kontext
    (die 'messages' fürs litellm-Completion) neu zusammengesetzt (siehe
    AgentSession.build_messages)."""
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
    temperature: float = Field(default=0.2, description="Sampling-Temperatur für LLM-Aufrufe dieses Agenten.")
    max_retries: int = Field(default=3, description="Maximale Wiederholungen bei Parse-Fehlern der finalen Antwort.")
    tools: list[WikiTool] = Field(default_factory=list, description="Werkzeuge, die der Agent per ReAct-Loop aufrufen kann.")
    max_tool_iterations: int = Field(default=15, description="Maximale Anzahl an Tool-Aufruf-Runden (ReAct-Schritten) pro Session.")
    enable_context_compaction: bool = Field(
        default=False,
        description="Ob der ältere Gesprächsverlauf bei Bedarf per günstigem LLM verdichtet wird, um Tokens "
                     "zu sparen (siehe context_compactor.py). Sinnvoll für Agenten mit vielen ReAct-Runden.",
    )
    compaction_model: LLMModels = Field(default=LLMModels.GEMMA_26B, description="Günstiges Modell für die Kontext-Verdichtung.")
    compaction_threshold_chars: int = Field(default=30000, description="Ab wie vielen Zeichen im aktuellen Kontext eine Verdichtung ausgelöst wird.")
    compaction_keep_recent_rounds: int = Field(default=3, description="Wie viele der letzten ReAct-Runden beim Verdichten unangetastet bleiben.")
    require_tool_call_first_round: bool = Field(
        default=False,
        description="Erzwingt in der allerersten Runde eines Turns per tool_choice='required' einen "
                     "Tool-Aufruf, und wertet eine finale Antwort ohne JEDEN Tool-Aufruf als ungültig (Retry "
                     "statt Erfolg). Nur für Agenten sinnvoll, die laut Prompt IMMER mindestens ein Tool "
                     "nutzen müssen (z.B. TaskAgent: update_plan) - verhindert, dass das Modell eine "
                     "komplexe Aufgabe ungeprüft als 'erledigt' halluziniert, ohne je etwas getan zu haben.",
    )

    def build_response_format_prompt(self) -> str:
        """Erzeugt aus response_type automatisch die Anweisung fürs erwartete JSON-Antwortformat."""
        lines = [
            f'  "{field_name}": "<{field.description or field_name}>"'
            for field_name, field in self.response_type.model_fields.items()
        ]
        schema_block = "{\n" + ",\n".join(lines) + "\n}"
        if self.tools:
            return (
                "## Antwortformat und Werkzeugnutzung\n"
                "WICHTIGE REGELN:\n"
                "1. Wenn für die Anfrage Werkzeuge erforderlich oder sinnvoll sind (z.B. Dateien lesen, suchen, erstellen, bearbeiten oder verschieben), "
                "musst du ZUERST die entsprechenden Werkzeuge per Tool-Call aufrufen!\n"
                "2. Behaupte NIEMALS im Text einer Antwort, dass du eine Datei angelegt, geändert oder gelesen hast, "
                "ohne das Werkzeug dafür tatsächlich aufgerufen zu haben.\n"
                "3. Erst wenn alle benötigten Werkzeuge ausgeführt wurden (oder bei einfachen Antworten/Smalltalk ohne Werkzeuge), "
                "gibst du deine finale Antwort als valides JSON-Objekt nach folgendem Schema ab (ohne Markdown-Codeblock, ohne Text davor/danach):\n"
                + schema_block
            )
        return (
            "Antworte ausschließlich mit einem einzigen validen JSON-Objekt exakt nach folgendem Schema, "
            "ohne zusätzlichen Text, ohne Markdown-Codeblock:\n" + schema_block
        )

    def validate_input(self, input_data: Any) -> BaseModel:
        if isinstance(input_data, dict):
            return self.input_type.model_validate(input_data)
        elif isinstance(input_data, BaseModel):
            return self.input_type.model_validate(input_data.model_dump())
        raise ValueError(f"[{self.name}] input_data muss dict oder BaseModel sein.")

    def parse_response(self, raw_output: str) -> ParseResult:
        """
        Prüft den String gegen das response_type Schema.
        Generiert bei Fehlschlag einen detaillierten Text-Bericht für das LLM.
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
                input_val = err.get('input', 'Unbekannt')
                error_messages.append(f"- Feld '{field_path}': {msg}. (Deine Eingabe war: {input_val})")

            report = (
                "Die vorherige Antwort war ungültig und entsprach nicht dem geforderten JSON-Schema. "
                "Bitte korrigiere folgende Fehler zwingend:\n" + 
                "\n".join(error_messages) +
                "\n\nHier ist deine fehlerhafte rohe Antwort zur Referenz:\n" +
                f"```json\n{raw_output}\n```"
            )
            return ParseResult(status=AgentStatus.ERROR, error_report=report)

class LLMCall(BaseModel):
    """Ein einzelner LLM-Turn innerhalb einer AgentSession: entweder ein oder mehrere
    Tool-Aufrufe (status=TOOL_CALL), eine ungültige finale Antwort (status=ERROR)
    oder die valide finale Antwort (status=SUCCESS)."""
    agent_name: str
    status: AgentStatus
    input_data: BaseModel
    output_data: BaseModel | None = None
    error_message: str | None = None
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
            log_lines.extend(["--- ERROR ---", self.error_message or "Unbekannter Fehler"])
        log_lines.append("=========================================")
        return "\n".join(log_lines)

class AgentSession(BaseModel):
    """Eine ReAct-Session: von der ersten Eingabe über beliebig viele Tool-Aufrufe bis
    zur finalen strukturierten Antwort. 'messages' ist der vollständige Gesprächsverlauf
    und alleinige Quelle für den Kontext, der bei jedem LLM-Aufruf gesendet wird (siehe
    build_messages) – nichts wird daneben nochmal separat mitgeführt. 'history' ist die
    Turn-für-Turn-Bilanz (für Logging/Statistik und den finalen Erfolg/Ergebnis-Check)."""
    agent: WikiAgent
    first_input: BaseModel
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: datetime = Field(default_factory=datetime.now)
    messages: list[SessionMessage] = Field(default_factory=list)
    history: list[LLMCall] = Field(default_factory=list)
    log_path: str | None = Field(default=None, description="Pfad der Logdatei dieser Session (siehe SessionLogger) – über alle Turns hinweg dieselbe Datei.")

    def _system_message(self, extra_context: str | None = None) -> SessionMessage:
        system_content = f"{self.agent.system_prompt}\n\n{self.agent.build_response_format_prompt()}"
        if extra_context:
            system_content += f"\n\n{extra_context}"
        return SessionMessage(role=MessageRole.SYSTEM, content=system_content)

    def start(self, valid_input: BaseModel) -> None:
        """Initialisiert den Gesprächsverlauf eines Ein-Schritt-Task-Agenten mit
        System-Prompt und der kompletten Eingabe als JSON. Muss einmal zu Beginn der
        Session aufgerufen werden, bevor build_messages() sinnvolle Ergebnisse liefert."""
        self.messages.append(self._system_message())
        self.messages.append(SessionMessage(
            role=MessageRole.USER,
            content=f"Bitte verarbeite folgende Daten:\n\n```json\n{valid_input.model_dump_json(indent=2)}\n```",
        ))

    def start_chat(self, first_message: str, context: str | None = None) -> None:
        """Initialisiert den Gesprächsverlauf eines Chat-Agenten: System-Prompt (optional
        ergänzt um zusätzlichen Hintergrund-Kontext, z.B. die aktuelle ai_map, damit der
        Agent den von Anfang an kennt statt ihn erst erfragen zu müssen) plus die erste
        Nutzer-Nachricht als reiner Text (keine JSON-Verpackung wie bei start()), damit
        sich das Ganze wie eine normale Unterhaltung liest."""
        self.messages.append(self._system_message(context))
        self.messages.append(SessionMessage(role=MessageRole.USER, content=first_message))

    def add_user_message(self, message: str) -> None:
        """Hängt eine weitere Nutzer-Nachricht an eine bereits laufende Chat-Session an
        (z.B. eine Folgefrage), ohne die bisherige Historie zu verlieren."""
        self.messages.append(SessionMessage(role=MessageRole.USER, content=message))

    def build_messages(self) -> list[dict]:
        """Setzt den vollständigen litellm-Kontext aus dem bisherigen Gesprächsverlauf
        (self.messages) zusammen. Der Kontext für jeden LLM-Aufruf entsteht also
        ausschließlich aus der Session selbst, nicht aus einer separaten Variable."""
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