from fastapi import APIRouter, HTTPException
import time
from ..core.config import get_settings
from ..services.observability_service import _is_real_mode, _amp_list_services, _amp_query_range

router = APIRouter()

@router.get("/container")
async def get_container_metrics(
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
        {"suffix": "cpu_usage", "unit": "%", "query": settings.amp_cpu_query},
        {"suffix": "memory_usage", "unit": "%", "query": settings.amp_memory_query},
    ]

    results = []
    for svc in services:
        for spec in metric_specs:
            query = spec["query"].replace("$service", svc)
            result = _amp_query_range(settings, query, start, end, step)
            values = result[0].get("values", []) if result else []
            points = []
            for item in values:
                if isinstance(item, list) and len(item) == 2:
                    try:
                        points.append({"ts": int(float(item[0]) * 1000), "value": float(item[1])})
                    except (TypeError, ValueError):
                        pass
            if not points:
                continue
            results.append({
                "id": f"{svc}_{spec['suffix']}",
                "name": f"{svc}_{spec['suffix']}",
                "unit": spec["unit"],
                "service": svc,
                "points": points,
            })
    if limit is not None and isinstance(results, list):
        return results[:limit]
    return results
