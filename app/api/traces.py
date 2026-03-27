import asyncio
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..services.observability_service import get_trace_detail, list_traces
from ..services.streaming_service import (
    encode_sse_event,
    ensure_stream_started,
    get_latest_stream_cursor,
    get_stream_backlog,
    subscribe_stream,
    unsubscribe_stream,
)

router = APIRouter(prefix="/v1", tags=["traces"])


@router.get("/traces")
def get_traces(
    service: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict:
    result = list_traces(service=service, status=status, limit=limit, offset=offset, start_time=start_time, end_time=end_time)
    if "__error__" in result:
        raise HTTPException(
            status_code=int(result.get("__status__", 502)),
            detail=str(result.get("__error__")),
        )
    return result


@router.get("/traces/backlog")
async def get_traces_backlog(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    await ensure_stream_started("traces")
    return get_stream_backlog("traces", cursor, limit)


@router.get("/traces/stream")
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


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    trace = get_trace_detail(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return trace
