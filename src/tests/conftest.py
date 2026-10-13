"""Globale Test-Infrastruktur.

WICHTIG: Mehrere Module frieren den Vault-Pfad (``WATCH_DIR``) und ``LOG_DIR`` beim
IMPORT ein. Deshalb werden die Umgebungsvariablen hier ganz oben gesetzt, bevor
irgendein ``src``-Modul importiert wird. Der Vault liegt für alle Tests unter demselben
Pfad und wird vor jedem Test geleert und frisch aus ``data.example/`` befüllt.
"""
import os
import shutil
import tempfile
from pathlib import Path

if "_OVA_TEST_ROOT" not in os.environ:
    os.environ["_OVA_TEST_ROOT"] = tempfile.mkdtemp(prefix="ova-tests-")
_TEST_ROOT = Path(os.environ["_OVA_TEST_ROOT"])
VAULT_DIR = (_TEST_ROOT / "vault").resolve()
LOG_DIR = _TEST_ROOT / "logs"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

os.environ["WATCH_DIR"] = str(VAULT_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)
if os.getenv("OVA_LIVE_TESTS") != "1":
    os.environ["GEMINI_API_KEY"] = "test-key"

import itertools  # noqa: E402

import httpx  # noqa: E402

# Kompatibilität: httpx >= 0.28 entfernte das 'app='-Keyword, das älteres starlette.testclient noch übergibt
_orig_httpx_init = httpx.Client.__init__
httpx.Client.__init__ = lambda self, *a, **k: _orig_httpx_init(
    self, *a, **{k_: v for k_, v in k.items() if k_ != "app"}
)

import litellm  # noqa: E402
import pytest  # noqa: E402

EXAMPLE_VAULT = Path(__file__).resolve().parents[2] / "data.example"


def _fill_vault() -> Path:
    for child in VAULT_DIR.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(EXAMPLE_VAULT, VAULT_DIR, dirs_exist_ok=True)
    return VAULT_DIR


# --------------------------------------------------------------------------- Vault


@pytest.fixture(autouse=True)
def vault() -> Path:
    """Frischer Test-Vault (Kopie von data.example) für JEDEN Test."""
    return _fill_vault()


# --------------------------------------------------------------------------- Netzwerk-Sperre


def _forbidden(name: str):
    def _boom(*args, **kwargs):
        raise AssertionError(f"Echter {name}-Aufruf im Test! Passende Fake-Fixture benutzen.")
    return _boom


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, request):
    """Sicherheitsnetz: ohne Fake-Fixture schlägt jeder externe Aufruf laut fehl."""
    if request.node.get_closest_marker("live"):
        yield
        return
    import src.agentic.agents.reasoner as reasoner
    import src.agentic.agents.web_search as web_search

    monkeypatch.setattr(litellm, "completion", _forbidden("litellm.completion"))
    monkeypatch.setattr(web_search, "_get_client", _forbidden("google.genai"))
    monkeypatch.setattr(web_search, "_client", None)
    monkeypatch.setattr(reasoner, "Agent", _forbidden("google.antigravity.Agent"))
    yield


# --------------------------------------------------------------------------- Fakes


@pytest.fixture
def fake_llm(monkeypatch, _no_network):
    """Ersetzt litellm.completion durch einen skriptbaren FakeLLM (siehe fakes/fake_llm.py)."""
    from src.tests.fakes.fake_llm import FakeLLM

    fake = FakeLLM()
    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr("src.agentic.llm_engine.supports_tool_choice", lambda model: True)
    yield fake
    fake.assert_clean()


@pytest.fixture
def fake_genai(monkeypatch, _no_network):
    from src.tests.fakes.fake_genai import FakeGenAIClient

    client = FakeGenAIClient()
    monkeypatch.setattr("src.agentic.agents.web_search._get_client", lambda: client)
    return client


@pytest.fixture
def fake_antigravity(monkeypatch, _no_network):
    from src.tests.fakes.fake_antigravity import FakeAntigravity

    fake = FakeAntigravity()
    monkeypatch.setattr("src.agentic.agents.reasoner.Agent", fake)
    return fake


# --------------------------------------------------------------------------- Threads & globaler Zustand


class _SyncThread:
    """Ersatz für threading.Thread, der das Target direkt in start() ausführt."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)

    def join(self, timeout=None):
        return None


@pytest.fixture
def sync_threads(monkeypatch):
    """Lässt start_background_task synchron laufen (Task-Agent im selben Thread)."""
    monkeypatch.setattr("src.agentic.agents.task_agent.threading.Thread", _SyncThread)


@pytest.fixture(autouse=True)
def _reset_global_state(monkeypatch):
    from src.agentic.agents import librarian, task_agent
    from src.routes.session import storage

    task_agent._jobs.clear()
    storage._sessions.clear()
    monkeypatch.setattr(librarian, "_rotation", itertools.cycle(librarian._MODEL_ROTATION))
    monkeypatch.setattr(task_agent, "_rotation", itertools.cycle(task_agent._MODEL_ROTATION))
    yield
    task_agent._jobs.clear()
    storage._sessions.clear()
