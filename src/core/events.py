# src/core/events.py
import asyncio
import threading
from typing import Dict, Any


class VaultEventBroadcaster:
    """Verwaltet Subscriptions für Echtzeit-Ereignisse (SSE) im Vault.
    Thread-safe, sodass Watchdog-Events aus Hintergrund-Threads sicher an
    asynchrone SSE-Clients weitergeleitet werden.
    """

    def __init__(self):
        self._subscribers: Dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}
        self._lock = threading.Lock()

    def subscribe(self, loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Queue:
        if loop is None:
            loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers[q] = loop
        return q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            self._subscribers.pop(q, None)

    def broadcast(self, event_type: str = "change", data: dict[str, Any] | None = None):
        payload = {"type": event_type, "data": data or {}}
        with self._lock:
            for q, loop in list(self._subscribers.items()):
                try:
                    if not loop.is_closed():
                        loop.call_soon_threadsafe(q.put_nowait, payload)
                except Exception:
                    pass


vault_events = VaultEventBroadcaster()
