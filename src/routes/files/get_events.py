# src/routes/files/get_events.py
import asyncio
import json
from fastapi import Request
from fastapi.responses import StreamingResponse

from src.core.events import vault_events
from src.routes.files import router


@router.get("/events")
async def get_events(request: Request):
    """Server-Sent Events (SSE) stream for file changes in the vault.

    Sends real-time messages to the frontend as soon as files are created, modified,
    moved or deleted, so the left sidebar updates automatically.
    """
    queue = vault_events.subscribe()

    async def event_generator():
        try:
            # Send an immediate "connected" event so the client knows the connection is up
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

            while True:
                # Check whether the client has disconnected
                if await request.is_disconnected():
                    break

                try:
                    # Warte auf ein Event oder sende alle 15 Sekunden einen Keep-Alive Ping
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    event_type = event.get("type", "change")
                    data = event.get("data", {})
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-Alive Ping
                    yield ": ping\n\n"
        finally:
            vault_events.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
