import os
from pathlib import Path
import pytest

from src.agentic.agents.chat import start_wiki_chat

# Skip unless OVA_LIVE_TESTS=1
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("OVA_LIVE_TESTS") != "1" or not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "test-key",
        reason="Live-Tests erfordern OVA_LIVE_TESTS=1 und einen echten GEMINI_API_KEY",
    ),
]


def test_live_chat_create_file(vault: Path):
    session = start_wiki_chat("Erstelle bitte eine Datei unter Kulturen/LiveTest.md mit dem Inhalt: Live-Test erfolgreich.")
    assert session.is_successful
    target = vault / "Kulturen" / "LiveTest.md"
    assert target.exists()
    assert "Live-Test erfolgreich" in target.read_text(encoding="utf-8")
