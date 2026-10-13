"""Skriptbare, agent-bewusste Attrappe für ``litellm.completion``.

Alle WikiAgents (Chat, TaskAgent, Librarian, Summarizer, FolderSummarizer) und der
ContextCompactor rufen ``litellm.completion`` auf. Da Agenten sich gegenseitig aufrufen
(Chat -> ask_librarian -> Librarian-Session), routet der FakeLLM jeden Aufruf anhand der
System-Nachricht zum richtigen Agenten und arbeitet für jeden Agenten ein eigenes Skript ab.

Beispiel::

    fake_llm.script("Chat",
        tool_calls(("create_file", {"path": "Kulturen/Zeta.md", "content": "abc"})),
        final({"reply": "Datei 'Kulturen/Zeta.md' wurde erstellt."}),
    )
    session = start_wiki_chat("Erstelle Kulturen/Zeta.md mit Inhalt abc")
    call = fake_llm.calls_for("Chat")[0]
    assert "create_file" in call.tool_names

Ein Skript-Eintrag kann sein:
- ein Response-Objekt (siehe ``response``/``tool_calls``/``final``/``raw``),
- eine Exception-Instanz oder -Klasse (wird beim Aufruf geworfen),
- ein Callable ``(kwargs) -> Response`` für dynamische Antworten.

Wichtig: ``_run_turn`` fängt Exceptions aus ``litellm.completion`` ab. Damit ein fehlendes
Skript nicht unbemerkt als "API-Fehler" durchrutscht, merkt sich der FakeLLM solche
unerwarteten Aufrufe; die ``fake_llm``-Fixture lässt den Test dann am Ende fehlschlagen.
"""
from __future__ import annotations

import itertools
import json
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from types import SimpleNamespace as NS
from typing import Any, Callable

_ids = itertools.count(1)


# --------------------------------------------------------------------------- Builder


def make_tool_call(name: str, arguments: dict | None = None, raw_arguments: str | None = None) -> NS:
    """Ein einzelner Tool-Call im Format, das ``_run_turn`` liest
    (``tc.id``, ``tc.function.name``, ``tc.function.arguments``)."""
    args_json = raw_arguments if raw_arguments is not None else json.dumps(arguments or {}, ensure_ascii=False)
    return NS(id=f"call_{next(_ids)}", type="function", function=NS(name=name, arguments=args_json))


def response(content: str | None = None, tool_calls_list: list | None = None,
             prompt_tokens: int = 100, completion_tokens: int = 20, usage: bool = True) -> NS:
    """Generische litellm-kompatible Antwort (``choices[0].message`` + ``usage``)."""
    message = NS(role="assistant", content=content, tool_calls=tool_calls_list or None)
    return NS(
        choices=[NS(index=0, message=message, finish_reason="tool_calls" if tool_calls_list else "stop")],
        usage=NS(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens) if usage else None,
    )


def tool_calls(*calls: tuple, content: str | None = None) -> NS:
    """Antwort mit einem oder mehreren Tool-Calls.

    Jeder Eintrag ist ``(name, arguments_dict)`` oder ``(name, None, raw_arguments_str)``.
    """
    built = []
    for call in calls:
        if len(call) == 3:
            built.append(make_tool_call(call[0], call[1], raw_arguments=call[2]))
        else:
            built.append(make_tool_call(call[0], call[1]))
    return response(content=content, tool_calls_list=built)


def final(data: dict) -> NS:
    """Finale, strukturierte JSON-Antwort."""
    return response(content=json.dumps(data, ensure_ascii=False))


def raw(text: str) -> NS:
    """Beliebiger Rohtext als Antwort (z.B. ungültiges JSON)."""
    return response(content=text)


# --------------------------------------------------------------------------- Aufzeichnung


@dataclass
class RecordedCall:
    agent: str
    kwargs: dict[str, Any]

    @property
    def messages(self) -> list[dict]:
        return self.kwargs.get("messages", [])

    @property
    def model(self) -> str:
        return str(self.kwargs.get("model"))

    @property
    def tools(self) -> list[dict]:
        return self.kwargs.get("tools") or []

    @property
    def tool_names(self) -> list[str]:
        return [t["function"]["name"] for t in self.tools]

    def tool_schema(self, name: str) -> dict:
        for t in self.tools:
            if t["function"]["name"] == name:
                return t["function"]
        raise KeyError(f"Tool '{name}' wurde in diesem Call nicht angeboten: {self.tool_names}")

    @property
    def system_prompt(self) -> str:
        if self.messages and self.messages[0].get("role") == "system":
            return self.messages[0].get("content") or ""
        return ""

    @property
    def user_messages(self) -> list[str]:
        return [m.get("content") or "" for m in self.messages if m.get("role") == "user"]

    @property
    def last_user_message(self) -> str:
        users = self.user_messages
        return users[-1] if users else ""

    @property
    def tool_results(self) -> list[str]:
        return [m.get("content") or "" for m in self.messages if m.get("role") == "tool"]

    def tool_result_for(self, tool_call_id: str) -> str:
        for m in self.messages:
            if m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id:
                return m.get("content") or ""
        raise KeyError(tool_call_id)


@dataclass
class FakeLLM:
    calls: list[RecordedCall] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    _scripts: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))
    _matchers: list[tuple[str, str]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self._register_defaults()

    # ----------------------------------------------------------------- Routing

    def _register_defaults(self) -> None:
        from src.agentic.agents.chat import ChatAgent
        from src.agentic.context_compactor import COMPACTION_SYSTEM_PROMPT
        from src.agentic.agents.folder_summarizer import FolderSummarizerAgent
        from src.agentic.agents.librarian import LibrarianAgent
        from src.agentic.agents.summarizer import SummarizerAgent
        from src.agentic.agents.task_agent import TaskAgent

        for agent in (ChatAgent, TaskAgent, LibrarianAgent, SummarizerAgent, FolderSummarizerAgent):
            self.register(agent.name, agent.system_prompt)
        self.register("Compactor", COMPACTION_SYSTEM_PROMPT)

    def register(self, name: str, system_prompt: str) -> None:
        """Registriert einen (Test-)Agenten. Später registrierte Agenten gewinnen."""
        self._matchers.insert(0, (name, system_prompt))

    def identify(self, messages: list[dict]) -> str:
        if not messages or messages[0].get("role") != "system":
            return "unknown"
        system = messages[0].get("content") or ""
        for name, prompt in self._matchers:
            if system.startswith(prompt):
                return name
        return "unknown"

    # ----------------------------------------------------------------- Skript

    def script(self, agent: str, *responses: Any) -> "FakeLLM":
        with self._lock:
            self._scripts[agent].extend(responses)
        return self

    def pending(self, agent: str | None = None) -> int:
        if agent is not None:
            return len(self._scripts[agent])
        return sum(len(q) for q in self._scripts.values())

    def __call__(self, **kwargs: Any) -> Any:
        agent = self.identify(kwargs.get("messages", []))
        with self._lock:
            self.calls.append(RecordedCall(agent=agent, kwargs=kwargs))
            queue = self._scripts[agent]
            if not queue:
                msg = f"Unerwarteter LLM-Call für Agent '{agent}' (kein Skript-Eintrag mehr übrig)."
                self.unexpected.append(msg)
                raise AssertionError(msg)
            item = queue.popleft()

        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item("Fake-Fehler")
        if callable(item):
            return item(kwargs)
        return item

    # ----------------------------------------------------------------- Auswertung

    def calls_for(self, agent: str) -> list[RecordedCall]:
        return [c for c in self.calls if c.agent == agent]

    def last_call(self, agent: str) -> RecordedCall:
        calls = self.calls_for(agent)
        assert calls, f"Kein LLM-Call für Agent '{agent}' aufgezeichnet. Aufgezeichnet: {[c.agent for c in self.calls]}"
        return calls[-1]

    def assert_clean(self) -> None:
        """Keine unerwarteten Aufrufe und alle geskripteten Antworten verbraucht."""
        assert not self.unexpected, "\n".join(self.unexpected)
        leftovers = {a: len(q) for a, q in self._scripts.items() if q}
        assert not leftovers, f"Nicht verbrauchte Skript-Antworten: {leftovers}"


def tool_call_factory(name: str, arguments_fn: Callable[[dict], dict]) -> Callable[[dict], NS]:
    """Dynamischer Skript-Eintrag: baut die Tool-Argumente aus den Request-kwargs."""
    def _build(kwargs: dict) -> NS:
        return tool_calls((name, arguments_fn(kwargs)))
    return _build
