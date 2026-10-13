import pytest

import src.agentic.agents.web_search as web_search_mod
from src.agentic.agents.web_search import (
    MODEL,
    SYSTEM_INSTRUCTION,
    web_search,
    _extract_sources,
)
from types import SimpleNamespace as NS


def test_web_search_arguments_and_sources_attached(fake_genai):
    fake_genai.text = "Batch pipelines are typically scheduled daily."
    fake_genai.sources = [
        ("NASA Breakthrough", "https://nasa.gov/warp"),
        ("ESA Propulsion", "https://esa.int/warp"),
    ]

    res = web_search("Ist Warp realistisch?")
    assert "Batch pipelines are typically scheduled daily." in res
    assert "NASA Breakthrough (https://nasa.gov/warp)" in res
    assert "ESA Propulsion (https://esa.int/warp)" in res

    call = fake_genai.calls[0]
    assert call["agent"] == web_search_mod.AGENT
    assert call["environment"] == "remote"
    assert call["agent_config"]["model"] == MODEL
    assert SYSTEM_INSTRUCTION in call["contents"]
    assert "Ist Warp realistisch?" in call["contents"]


def test_web_search_deduplicates_sources():
    # Test _extract_sources directly with duplicate URLs
    candidate = NS(
        grounding_metadata=NS(
            grounding_chunks=[
                NS(web=NS(uri="https://duplicate.com", title="Title 1")),
                NS(web=NS(uri="https://duplicate.com", title="Title 2")),
                NS(web=NS(uri="https://unique.com", title="Title 3")),
            ]
        )
    )
    resp = NS(candidates=[candidate])
    sources = _extract_sources(resp)
    assert len(sources) == 2
    assert "Title 1 (https://duplicate.com)" in sources
    assert "Title 3 (https://unique.com)" in sources


def test_web_search_empty_response(fake_genai):
    fake_genai.text = ""
    res = web_search("Is daily batch still common practice?")
    assert "Error: the web search returned no answer." in res


def test_web_search_exception_handled(fake_genai):
    fake_genai.exc = ConnectionError("Network unreachable")
    res = web_search("Test")
    assert "Error: the web search could not be performed" in res
    assert "Network unreachable" in res


def test_web_search_get_client_is_singleton(monkeypatch):
    dummy_client = object()
    monkeypatch.setattr("google.genai.Client", lambda: dummy_client)
    
    local_ns = {"_client": None, "genai": web_search_mod.genai}
    exec(
        "def _get_client():\n"
        "    global _client\n"
        "    if _client is None:\n"
        "        _client = genai.Client()\n"
        "    return _client\n",
        local_ns,
    )
    get_client_fn = local_ns["_get_client"]
    c1 = get_client_fn()
    c2 = get_client_fn()
    assert c1 is dummy_client
    assert c2 is dummy_client
    assert c1 is c2
