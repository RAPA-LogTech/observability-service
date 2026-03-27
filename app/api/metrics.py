import asyncio
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..services.observability_service import list_metrics, list_service_health
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
async def get_metrics(
    service: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int | None = None,
) -> object:
    import asyncio
    result = await asyncio.get_event_loop().run_in_executor(None, lambda: list_metrics(service=service, start=start, end=end))
    if isinstance(result, dict) and "__error__" in result:
        raise HTTPException(
            status_code=int(result.get("__status__", 502)),
            detail=str(result.get("__error__")),
        )
    if limit is not None and isinstance(result, list):
        return result[:limit]
    return result


@router.get("/metrics/health")
async def get_metrics_health() -> list:
    return await asyncio.get_event_loop().run_in_executor(None, list_service_health)


@router.get("/metrics/debug-labels")
def get_debug_labels(metric: str = "app_http_server_5xx_error_ratio_5m") -> list:
    """AMP 메트릭의 실제 label 구조 확인용 임시 엔드포인트"""
    from ..services.observability_service import _amp_instant_query, get_settings, _is_real_mode
    settings = get_settings()
    if not _is_real_mode(settings) or not settings.amp_endpoint:
        return []
    result = _amp_instant_query(settings, metric)
    return [item.get("metric", {}) for item in result]


@router.get("/metrics/services")
def get_metric_services() -> list[str]:
    from ..services.observability_service import _amp_list_services, get_settings, _is_real_mode
    settings = get_settings()
    if not _is_real_mode(settings) or not settings.amp_endpoint:
        return []
    return _amp_list_services(settings)


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
