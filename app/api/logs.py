import asyncio
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..services.observability_service import list_logs
from ..services.streaming_service import (
    encode_sse_event,
    ensure_stream_started,
    get_latest_stream_cursor,
    get_stream_backlog,
    subscribe_stream,
    unsubscribe_stream,
)

router = APIRouter(prefix="/v1", tags=["logs"])


@router.get("/logs")
def get_logs(
    service: str | None = None,
    level: str | None = None,
    env: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
) -> dict:
    return list_logs(service=service, level=level, env=env, limit=limit, offset=offset)


@router.get("/logs/backlog")
async def get_logs_backlog(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    await ensure_stream_started("logs")
    return get_stream_backlog("logs", cursor, limit)


@router.get("/logs/stream")
async def stream_logs(request: Request) -> StreamingResponse:
    await ensure_stream_started("logs")
    queue = subscribe_stream("logs")

    async def event_generator():
        try:
            yield "retry: 2000\n\n"
            yield f": latest-cursor {get_latest_stream_cursor('logs')}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield encode_sse_event("log", payload)
                except asyncio.TimeoutError:
                    yield f": ping {int(time.time() * 1000)}\n\n"
        finally:
            unsubscribe_stream("logs", queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
