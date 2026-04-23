import time

from fastapi import APIRouter

from ..core.config import get_settings
from ..services.observability_service import _amp_query_range

router = APIRouter()


@router.get("/container")
async def get_container_metrics():
    settings = get_settings()
    # 최근 5분 구간, step=60초
    end_ts = int(time.time())
    start_ts = end_ts - 300
    step_seconds = 60
    cpu = _amp_query_range(
        settings, "app_container_cpu_utilization_avg_5m", start_ts, end_ts, step_seconds
    )
    mem = _amp_query_range(
        settings, "app_container_memory_utilization_avg_5m", start_ts, end_ts, step_seconds
    )
    return {"cpu": cpu, "memory": mem}
