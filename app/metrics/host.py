import time

from fastapi import APIRouter

from ..core.config import get_settings
from ..services.observability_service import _amp_query_range

router = APIRouter()


@router.get("/host")
async def get_host_metrics():
    settings = get_settings()
    end_ts = int(time.time())
    start_ts = end_ts - 300
    step_seconds = 60
    mem = _amp_query_range(settings, "host_memory_usage_avg_5m", start_ts, end_ts, step_seconds)
    net_rx = _amp_query_range(settings, "host_network_rx_bytes_5m", start_ts, end_ts, step_seconds)
    net_tx = _amp_query_range(settings, "host_network_tx_bytes_5m", start_ts, end_ts, step_seconds)
    return {
        "memory": mem,
        "network_rx": net_rx,
        "network_tx": net_tx,
    }
