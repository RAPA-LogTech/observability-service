
from fastapi import APIRouter, HTTPException
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from ..core.config import get_settings
from ..services.observability_service import _is_real_mode, _amp_list_services, _amp_query_range

router = APIRouter()

@router.get("/infra")
async def get_infra_metrics(
    service: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int | None = None,
) -> object:
    settings = get_settings()
    if not _is_real_mode(settings):
        return []
    if not settings.amp_endpoint:
        raise HTTPException(status_code=503, detail="DATA_SOURCE_MODE is real but AMP_ENDPOINT is not configured")

    services = [service] if service else _amp_list_services(settings)
    if not services:
        return []

    now = int(time.time())
    end = end or now
    start = start or (end - 60)
    step = max(60, settings.amp_step_seconds)


    metric_specs = [
        {"suffix": "cpu_usage", "unit": "%", "query": settings.amp_cpu_query, "type": "container"},
        {"suffix": "memory_usage", "unit": "%", "query": settings.amp_memory_query, "type": "container"},
        {"suffix": "host_memory_usage", "unit": "%", "query": 'host_memory_usage_avg_5m{instance!=""} * 100', "type": "host"},
        {"suffix": "host_network_rx_bytes", "unit": "bytes", "query": 'host_network_rx_bytes_5m{instance!=""}', "type": "host"},
        {"suffix": "host_network_tx_bytes", "unit": "bytes", "query": 'host_network_tx_bytes_5m{instance!=""}', "type": "host"},
    ]

    tasks = [(svc, spec) for svc in services for spec in metric_specs]

    def _fetch(svc: str, spec: dict) -> tuple[str, dict, list]:
        query = spec["query"].replace("$service", svc) if "$service" in spec["query"] else spec["query"]
        return svc, spec, _amp_query_range(settings, query, start, end, step)

    results: dict[tuple, list] = {}
    first_error: dict | None = None

    with ThreadPoolExecutor(max_workers=min(len(tasks), 10)) as executor:
        futures = {executor.submit(_fetch, svc, spec): (svc, spec) for svc, spec in tasks}
        for future in as_completed(futures):
            svc, spec, result = future.result()
            if result and isinstance(result[0], dict) and "__error__" in result[0]:
                if first_error is None:
                    first_error = result[0]
                continue
            results[(svc, spec["suffix"])] = result

    if first_error and not results:
        raise HTTPException(status_code=int(first_error.get("__status__", 502)), detail=str(first_error.get("__error__")))


    series_list: list[dict] = []
    for svc, spec in tasks:
        result = results.get((svc, spec["suffix"]), [])
        values = result[0].get("values", []) if result else []
        metric_type = spec.get("type", "container")
        points = []
        instance = None
        for item in values:
            if isinstance(item, list) and len(item) == 2:
                try:
                    points.append({"ts": int(float(item[0]) * 1000), "value": float(item[1])})
                except (TypeError, ValueError):
                    pass
        # instance 정보 추출 (host 메트릭의 경우)
        if metric_type == "host" and result and isinstance(result[0].get("metric"), dict):
            instance = result[0]["metric"].get("instance")
        if not points:
            continue
        entry = {
            "id": f"{svc}_{spec['suffix']}",
            "name": f"{svc}_{spec['suffix']}",
            "unit": spec["unit"],
            "service": svc,
            "points": points,
        }
        if instance:
            entry["instance"] = instance
        series_list.append(entry)

    if limit is not None and isinstance(series_list, list):
        return series_list[:limit]
    return series_list
