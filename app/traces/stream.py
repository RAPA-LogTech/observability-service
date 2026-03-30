from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from ..services.streaming_service import (
    encode_sse_event,
    ensure_stream_started,
    get_latest_stream_cursor,
    subscribe_stream,
    unsubscribe_stream,
)
import asyncio
import time

router = APIRouter()

@router.get("/stream")
async def stream_traces(request: Request) -> StreamingResponse:
    await ensure_stream_started("traces")
    queue = subscribe_stream("traces")

    async def event_generator():
        try:
            yield "retry: 2000\n\n"
            yield f": latest-cursor {get_latest_stream_cursor('traces')}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield encode_sse_event("trace", payload)
                except asyncio.TimeoutError:
                    yield f": ping {int(time.time() * 1000)}\n\n"
        finally:
            unsubscribe_stream("traces", queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
