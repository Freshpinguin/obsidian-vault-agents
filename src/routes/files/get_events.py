# src/routes/files/get_events.py
import asyncio
import json
from fastapi import Request
from fastapi.responses import StreamingResponse

from src.core.events import vault_events
from src.routes.files import router


@router.get("/events")
async def get_events(request: Request):
    """Server-Sent Events (SSE) Stream für Dateiänderungen im Vault.
    
    Sendet Echtzeit-Nachrichten an das Frontend, sobald Dateien erstellt, geändert,
    verschoben oder gelöscht werden, damit die linke Sidebar automatisch aktualisiert wird.
    """
    queue = vault_events.subscribe()

    async def event_generator():
        try:
            # Sofortiges "connected" Event senden, damit der Client weiß, dass die Verbindung steht
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

            while True:
                # Prüfen, ob der Client die Verbindung getrennt hat
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
