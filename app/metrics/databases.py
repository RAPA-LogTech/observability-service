import time

from fastapi import APIRouter, Query

from ..services.observability_service import _amp_query_range, get_settings

router = APIRouter()


def _extract_service(metric_labels: dict) -> str | None:
    candidates = [
        metric_labels.get("service"),
        metric_labels.get("service_name"),
        metric_labels.get("job"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        value = str(candidate)
        if "/" in value:
            value = value.rsplit("/", maxsplit=1)[-1]
        if value:
            return value
    return None


def _extract_instance(metric_labels: dict) -> str | None:
    candidates = [
        metric_labels.get("instance"),
        metric_labels.get("pod"),
        metric_labels.get("container"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


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
        {
            "name": "db_client_connections_pending_requests",
            "query": "db_client_connections_pending_requests",
        },
        {"name": "db_client_connections_max", "query": "db_client_connections_max"},
        {
            "name": "db_connection_use",
            "query": "histogram_quantile(0.95, sum(rate(db_connection_use_bucket[5m])) by (le,service))",
        },
        {
            "name": "db_connection_wait",
            "query": "histogram_quantile(0.95, sum(rate(db_connection_wait_bucket[5m])) by (le,service))",
        },
    ]

    results = []
    for q in queries:
        prom_result = _amp_query_range(
            settings, q["query"], int(start / 1000), int(end / 1000), step
        )
        for idx, series in enumerate(prom_result):
            metric_labels = (
                series.get("metric", {}) if isinstance(series.get("metric", {}), dict) else {}
            )
            service = _extract_service(metric_labels)
            instance = _extract_instance(metric_labels)
            scope = service or instance or f"all_{idx}"
            metric = {
                "id": f"{q['name']}_{scope}",
                "name": q["name"],
                "unit": "",
                "service": service,
                "instance": instance,
                "points": [
                    {"ts": int(float(p[0]) * 1000), "value": float(p[1])}
                    for p in series.get("values", [])
                ],
            }
            results.append(metric)

    return results


@router.get("/database")
def query_db_metrics_alias(
    start: int = Query(None, description="시작 타임스탬프(ms)", alias="start"),
    end: int = Query(None, description="끝 타임스탬프(ms)", alias="end"),
    step: int = Query(30, description="step(초)", alias="step"),
):
    # Backward-compatible alias for clients expecting singular path.
    return query_db_metrics(start=start, end=end, step=step)
