"""Global test infrastructure.

IMPORTANT: several modules freeze the vault path (``WATCH_DIR``) and ``LOG_DIR`` at
IMPORT time. The environment variables are therefore set at the very top here, before
any ``src`` module is imported. The vault lives at the same path for all tests and is
emptied and refilled from ``data.example/`` before each test.
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

# Compatibility: httpx >= 0.28 removed the 'app=' keyword that older starlette.testclient still passes
_orig_httpx_init = httpx.Client.__init__
httpx.Client.__init__ = lambda self, *a, **k: _orig_httpx_init(
    self, *a, **{k_: v for k_, v in k.items() if k_ != "app"}
)

import litellm  # noqa: E402
import pytest  # noqa: E402

# The tests get their own fixture vault rather than data.example: the example vault is
# demo content that changes whenever the demo changes, and 21 tests used to break the
# moment it did. This copy is owned by the test suite and only changes when a test needs
# it to.
EXAMPLE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


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
    """A fresh test vault (a copy of the fixture vault) for EVERY test."""
    return _fill_vault()


# ------------------------------------------------------------------------- Network lockdown


def _forbidden(name: str):
    def _boom(*args, **kwargs):
        raise AssertionError(f"Echter {name}-Aufruf im Test! Passende Fake-Fixture benutzen.")
    return _boom


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, request):
    """Safety net: without a fake fixture, any external call fails loudly."""
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
    monkeypatch.setattr("src.agentic.engine.runner.supports_tool_choice", lambda model: True)
    # No test should actually wait out the retry backoff of _completion_with_failover.
    monkeypatch.setattr("src.agentic.engine.runner.RETRY_BACKOFF_S", (0.0, 0.0))
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
    """A threading.Thread replacement that runs the target directly in start()."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)

    def join(self, timeout=None):
        return None


@pytest.fixture
def sync_threads(monkeypatch):
    """Runs start_background_task synchronously (task agent in the same thread)."""
    monkeypatch.setattr("src.agentic.engine.jobs.threading.Thread", _SyncThread)


@pytest.fixture(autouse=True)
def _reset_global_state(monkeypatch):
    from src.agentic.engine.jobs import _jobs
    from src.agentic.engine.model_rotation import librarian_rotation, task_rotation
    from src.routes.session import storage

    _jobs.clear()
    storage._sessions.clear()
    librarian_rotation.reset()
    task_rotation.reset()
    yield
    _jobs.clear()
    storage._sessions.clear()
    librarian_rotation.reset()
    task_rotation.reset()
