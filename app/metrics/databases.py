from fastapi import APIRouter, Query
from ..services.observability_service import get_settings, _amp_query_range
import time

router = APIRouter()

@router.get("/databases")
def query_db_metrics(
    start: int = Query(None, description="시작 타임스탬프(ms)", alias="start"),
    end: int = Query(None, description="끝 타임스탬프(ms)", alias="end"),
    step: int = Query(30, description="step(초)", alias="step"),
):
    """
    DB 커넥션 풀 관련 메트릭 시리즈만 반환
    - db_client_connections_usage
    - db_client_connections_pending_requests
    - db_client_connections_max
    - db_connection_use (p95)
    - db_connection_wait (p95)
    """
    settings = get_settings()
    now = int(time.time() * 1000)
    if not start:
        start = now - 5 * 60 * 1000
    if not end:
        end = now

    queries = [
        {"name": "db_client_connections_usage", "query": "db_client_connections_usage"},
        {"name": "db_client_connections_pending_requests", "query": "db_client_connections_pending_requests"},
        {"name": "db_client_connections_max", "query": "db_client_connections_max"},
        {"name": "db_connection_use", "query": "histogram_quantile(0.95, sum(rate(db_connection_use_bucket[5m])) by (le,service))"},
        {"name": "db_connection_wait", "query": "histogram_quantile(0.95, sum(rate(db_connection_wait_bucket[5m])) by (le,service))"},
    ]

    results = []
    for q in queries:
        prom_result = _amp_query_range(settings, q["query"], int(start/1000), int(end/1000), step)
        for series in prom_result:
            metric = {
                "id": f"{q['name']}_{series.get('metric', {}).get('service', 'all')}",
                "name": q["name"],
                "unit": "",
                "service": series.get("metric", {}).get("service"),
                "points": [
                    {"ts": int(float(p[0]) * 1000), "value": float(p[1])} for p in series.get("values", [])
                ],
            }
            results.append(metric)
    return results
