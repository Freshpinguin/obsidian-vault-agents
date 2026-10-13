"""Attrappe für den ``google.genai``-Client, den ``src.agentic.agents.web_search`` nutzt.

Beispiel::

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

    def generate_content(self, **kwargs: Any) -> NS:
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        chunks = [NS(web=NS(uri=uri, title=title)) for title, uri in self.sources]
        return NS(text=self.text, candidates=[NS(grounding_metadata=NS(grounding_chunks=chunks))])
