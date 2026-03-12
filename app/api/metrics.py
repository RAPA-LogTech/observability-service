import asyncio
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..services.observability_service import list_metrics
from ..services.streaming_service import (
    encode_sse_event,
    ensure_stream_started,
    get_latest_stream_cursor,
    get_stream_backlog,
    subscribe_stream,
    unsubscribe_stream,
)

router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get("/metrics")
def get_metrics(service: str | None = None) -> list[dict]:
    return list_metrics(service=service)


@router.get("/metrics/backlog")
async def get_metrics_backlog(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    await ensure_stream_started("metrics")
    return get_stream_backlog("metrics", cursor, limit)


@router.get("/metrics/stream")
async def stream_metrics(request: Request) -> StreamingResponse:
    await ensure_stream_started("metrics")
    queue = subscribe_stream("metrics")

    async def event_generator():
        try:
            yield "retry: 2000\n\n"
            yield f": latest-cursor {get_latest_stream_cursor('metrics')}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield encode_sse_event("metric", payload)
                except asyncio.TimeoutError:
                    yield f": ping {int(time.time() * 1000)}\n\n"
        finally:
            unsubscribe_stream("metrics", queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
