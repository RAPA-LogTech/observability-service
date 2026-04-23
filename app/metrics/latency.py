import time

from fastapi import APIRouter

from ..core.config import get_settings
from ..services.observability_service import _amp_query_range

router = APIRouter()


@router.get("/latency")
async def get_latency_metrics(
    service: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int | None = None,
) -> object:

    settings = get_settings()
    # start, end 파라미터가 있으면 사용, 없으면 최근 5분
    end_ts = end if end is not None else int(time.time())
    start_ts = start if start is not None else end_ts - 300
    step_seconds = 60
    latency_p95 = _amp_query_range(
        settings, "app_http_server_latency_p95_5m", start_ts, end_ts, step_seconds
    )
    return {"latency_p95": latency_p95}
