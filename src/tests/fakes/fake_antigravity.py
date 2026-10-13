"""Attrappe für ``google.antigravity.Agent``, den ``src.agents.reasoner`` nutzt.

Der echte Aufruf ist::

    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        text = await response.text()

Beispiel::

    fake = FakeAntigravity(reply="Ausgearbeiteter Text")
    monkeypatch.setattr("src.agents.reasoner.Agent", fake)
    run_reasoning("Denk nach")
    assert fake.prompts == ["Denk nach"]
"""
from __future__ import annotations

from typing import Any


class _FakeResponse:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    async def text(self) -> str:
        return self._reply


class _FakeAgentSession:
    def __init__(self, owner: "FakeAntigravity") -> None:
        self._owner = owner

    async def __aenter__(self) -> "_FakeAgentSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False

    async def chat(self, prompt: str) -> _FakeResponse:
        self._owner.prompts.append(prompt)
        if self._owner.exc is not None:
            raise self._owner.exc
        return _FakeResponse(self._owner.reply)


class FakeAntigravity:
    def __init__(self, reply: str = "Ergebnis des Denk-Agenten.", exc: BaseException | None = None) -> None:
        self.reply = reply
        self.exc = exc
        self.prompts: list[str] = []
        self.configs: list[Any] = []

    def __call__(self, config: Any) -> _FakeAgentSession:
        self.configs.append(config)
        return _FakeAgentSession(self)
