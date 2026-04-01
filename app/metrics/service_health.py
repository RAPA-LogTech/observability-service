from fastapi import APIRouter
from ..core.config import get_settings
from ..services.observability_service import _amp_query_range
import time

router = APIRouter()

@router.get("/health")
async def get_health():
    settings = get_settings()
    end_ts = int(time.time())
    start_ts = end_ts - 300
    step_seconds = 60
    error_4xx = _amp_query_range(settings, 'app_http_server_4xx_error_ratio_5m', start_ts, end_ts, step_seconds)
    error_5xx = _amp_query_range(settings, 'app_http_server_5xx_error_ratio_5m', start_ts, end_ts, step_seconds)
    return {
        "error_4xx": error_4xx,
        "error_5xx": error_5xx,
    }

@router.get("/service-health")
async def get_service_health():
    settings = get_settings()
    end_ts = int(time.time())
    start_ts = end_ts - 300
    step_seconds = 60
    error_4xx = _amp_query_range(settings, 'app_http_server_4xx_error_ratio_5m', start_ts, end_ts, step_seconds)
    error_5xx = _amp_query_range(settings, 'app_http_server_5xx_error_ratio_5m', start_ts, end_ts, step_seconds)
    return {
        "error_4xx": error_4xx,
        "error_5xx": error_5xx,
    }
