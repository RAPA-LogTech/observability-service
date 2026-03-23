import asyncio
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from ..services.observability_service import _opensearch_search, get_settings
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




# logs-app, logs-host 인덱스별 필터 옵션을 한 번에 반환
@router.get("/logs/filters")
async def get_log_filters() -> dict:
    """
    logs-app, logs-host 인덱스별로 필터 옵션(서비스, 환경, 레벨, 호스트)을 그룹화하여 반환
    """
    settings = get_settings()
    # logs-app: 서비스, 환경, 레벨, 호스트
    app_aggs = {
        "services": {"terms": {"field": "resource.service.name.keyword", "size": 100}},
        "envs": {"terms": {"field": "resource.deployment.environment.keyword", "size": 20}},
        "levels": {"terms": {"field": "severity.text.keyword", "size": 10}},
        "hosts": {"terms": {"field": "resource.host.name.keyword", "size": 100}},
    }
    # logs-app 인덱스만 명확히 조회
    app_result = _opensearch_search(settings, getattr(settings, "opensearch_app_logs_index", "logs-app"), {"size": 0, "aggs": app_aggs})
    # logs-host: 환경, 레벨, 호스트
    host_aggs = {
        "envs": {"terms": {"field": "resource.deployment.environment.keyword", "size": 20}},
        "levels": {"terms": {"field": "severity.text.keyword", "size": 10}},
        "hosts": {"terms": {"field": "resource.host.name.keyword", "size": 100}},
    }
    # logs-host 인덱스만 명확히 조회
    host_result = _opensearch_search(settings, getattr(settings, "opensearch_host_logs_index", "logs-host"), {"size": 0, "aggs": host_aggs})

    def extract_buckets(agg):
        return [b["key"] for b in agg.get("buckets", [])]

    # 오류 처리
    if "__error__" in app_result:
        return JSONResponse(status_code=502, content={"error": app_result["__error__"]})
    if "__error__" in host_result:
        return JSONResponse(status_code=502, content={"error": host_result["__error__"]})

    return {
        "logs-app": {
            "services": sorted(set(extract_buckets(app_result.get("aggregations", {}).get("services", {}))), key=str),
            "envs": sorted(set(extract_buckets(app_result.get("aggregations", {}).get("envs", {}))), key=str),
            "levels": sorted(set(extract_buckets(app_result.get("aggregations", {}).get("levels", {}))), key=str) or ["INFO", "WARN", "ERROR", "DEBUG"],
            "hosts": sorted(set(extract_buckets(app_result.get("aggregations", {}).get("hosts", {}))), key=str),
        },
        "logs-host": {
            "envs": sorted(set(extract_buckets(host_result.get("aggregations", {}).get("envs", {}))), key=str),
            "levels": sorted(set(extract_buckets(host_result.get("aggregations", {}).get("levels", {}))), key=str) or ["INFO", "WARN", "ERROR", "DEBUG"],
            "hosts": sorted(set(extract_buckets(host_result.get("aggregations", {}).get("hosts", {}))), key=str),
        },
    }


@router.get("/logs")
def get_logs(
    service: str | None = None,
    log_source: str | None = None,  # 로그 소스 필터 (app, host, all)
    level: str | None = None,
    env: str | None = None,
    cluster: str | None = None,
    startTime: int | None = None,
    endTime: int | None = None,
    customTags: str | None = None,  # JSON 직렬화된 문자열로 전달
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
) -> dict:
    tags = None
    if customTags:
        try:
            tags = json.loads(customTags)
        except Exception:
            tags = None
    result = list_logs(
        service=service,
        level=level,
        env=env,
        cluster=cluster,
        log_source=log_source,
        start_time=startTime,
        end_time=endTime,
        custom_tags=tags,
        limit=limit,
        offset=offset,
    )
    if "__error__" in result:
        raise HTTPException(
            status_code=int(result.get("__status__", 502)),
            detail=str(result.get("__error__")),
        )
    return result


@router.get("/logs/backlog")
async def get_logs_backlog(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
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
