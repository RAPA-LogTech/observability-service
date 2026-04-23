import time

from fastapi import APIRouter

from ..core.config import get_settings
from ..services.observability_service import _amp_query_range

router = APIRouter()


@router.get("/infra")
async def get_infra_summary():
    settings = get_settings()
    end_ts = int(time.time())
    start_ts = end_ts - 300
    step_seconds = 60
    container_cpu = _amp_query_range(
        settings, "app_container_cpu_utilization_avg_5m", start_ts, end_ts, step_seconds
    )
    container_mem = _amp_query_range(
        settings, "app_container_memory_utilization_avg_5m", start_ts, end_ts, step_seconds
    )
    host_memory = _amp_query_range(
        settings, "host_memory_usage_avg_5m", start_ts, end_ts, step_seconds
    )
    host_network_rx = _amp_query_range(
        settings, "host_network_rx_bytes_5m", start_ts, end_ts, step_seconds
    )
    host_network_tx = _amp_query_range(
        settings, "host_network_tx_bytes_5m", start_ts, end_ts, step_seconds
    )
    rds_cpu = _amp_query_range(settings, "rds_cpu_utilization", start_ts, end_ts, step_seconds)
    rds_conn = _amp_query_range(
        settings, "rds_database_connections", start_ts, end_ts, step_seconds
    )
    db_usage = _amp_query_range(
        settings, "db_client_connections_usage", start_ts, end_ts, step_seconds
    )
    db_pending = _amp_query_range(
        settings, "db_client_connections_pending_requests", start_ts, end_ts, step_seconds
    )
    db_max = _amp_query_range(settings, "db_client_connections_max", start_ts, end_ts, step_seconds)
    db_wait_p95 = _amp_query_range(
        settings,
        "histogram_quantile(0.95, sum(rate(db_client_connections_wait_time_milliseconds_bucket[5m])) by (le))",
        start_ts,
        end_ts,
        step_seconds,
    )
    db_use_p95 = _amp_query_range(
        settings,
        "histogram_quantile(0.95, sum(rate(db_client_connections_use_time_milliseconds_bucket[5m])) by (le))",
        start_ts,
        end_ts,
        step_seconds,
    )
    return {
        "container_cpu": container_cpu,
        "container_mem": container_mem,
        "host_memory": host_memory,
        "host_network_rx": host_network_rx,
        "host_network_tx": host_network_tx,
        "rds_cpu": rds_cpu,
        "rds_conn": rds_conn,
        "db_usage": db_usage,
        "db_pending": db_pending,
        "db_max": db_max,
        "db_wait_p95": db_wait_p95,
        "db_use_p95": db_use_p95,
    }
