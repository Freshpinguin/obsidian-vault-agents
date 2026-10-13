"""Fake for the ``google.genai`` client used by ``src.agentic.agents.web_search``.

Example::

    fake = FakeGenAIClient(text="Warp ist spekulativ.", sources=[("NASA", "https://nasa.gov/warp")])
    monkeypatch.setattr("src.agentic.agents.web_search._get_client", lambda: fake)
    web_search("Ist Warp realistisch?")
    assert fake.calls[0]["model"] == web_search_module.MODEL
"""
from __future__ import annotations

from types import SimpleNamespace as NS
from typing import Any


class FakeGenAIClient:
    def __init__(self, text: str | None = "Antwort aus dem Web.",
                 sources: list[tuple[str | None, str]] | None = None,
                 exc: BaseException | None = None) -> None:
        self.text = text
        self.sources = sources or []
        self.exc = exc
        self.calls: list[dict[str, Any]] = []
        self.models = self  # client.models.generate_content(...)
        self.interactions = self  # client.interactions.create(...)

    def generate_content(self, **kwargs: Any) -> NS:
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        chunks = [NS(web=NS(uri=uri, title=title)) for title, uri in self.sources]
        return NS(text=self.text, output_text=self.text, candidates=[NS(grounding_metadata=NS(grounding_chunks=chunks))])

    def create(self, **kwargs: Any) -> NS:
        call_info = dict(kwargs)
        if "agent_config" in kwargs and isinstance(kwargs["agent_config"], dict):
            call_info["model"] = kwargs["agent_config"].get("model")
        if "input" in kwargs:
            call_info["contents"] = kwargs["input"]
        call_info["config"] = NS(tools=[NS(google_search=NS())])
        self.calls.append(call_info)
        if self.exc is not None:
            raise self.exc
        chunks = [NS(web=NS(uri=uri, title=title)) for title, uri in self.sources]
        return NS(output_text=self.text, text=self.text, candidates=[NS(grounding_metadata=NS(grounding_chunks=chunks))])
