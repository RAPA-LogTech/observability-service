import json

from fastapi import APIRouter, Query, Response

from ..services.observability_service import list_logs

router = APIRouter()


@router.get("/")
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
) -> Response:
    tags = None
    if customTags:
        try:
            tags = json.loads(customTags)
        except (json.JSONDecodeError, ValueError, TypeError):
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
    return Response(
        content=json.dumps(result),
        media_type="application/json",
        status_code=int(result.get("__status__", 200)) if "__status__" in result else 200,
    )
