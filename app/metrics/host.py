from fastapi import APIRouter, HTTPException
import time
from ..core.config import get_settings
from ..services.observability_service import _is_real_mode, _amp_query_range

router = APIRouter()

@router.get("/v1/metrics/host")
async def get_host_metrics(
    start: int | None = None,
    end: int | None = None,
    limit: int | None = None,
) -> object:
    settings = get_settings()
    if not _is_real_mode(settings):
        return []
    if not settings.amp_endpoint:
        raise HTTPException(status_code=503, detail="DATA_SOURCE_MODE is real but AMP_ENDPOINT is not configured")

    now = int(time.time())
    end = end or now
    start = start or (end - 60)
    step = max(60, settings.amp_step_seconds)

    metric_specs = [
        {"suffix": "host_memory_usage", "unit": "%", "query": 'host_memory_usage_avg_5m{instance!=""} * 100'},
        {"suffix": "host_network_rx_bytes", "unit": "bytes", "query": 'host_network_rx_bytes_5m{instance!=""}'},
        {"suffix": "host_network_tx_bytes", "unit": "bytes", "query": 'host_network_tx_bytes_5m{instance!=""}'},
    ]

    results = []
    for spec in metric_specs:
        query = spec["query"]
        result = _amp_query_range(settings, query, start, end, step)
        values = result[0].get("values", []) if result else []
        instance = result[0]["metric"].get("instance") if result and isinstance(result[0].get("metric"), dict) else None
        points = []
        for item in values:
            if isinstance(item, list) and len(item) == 2:
                try:
                    points.append({"ts": int(float(item[0]) * 1000), "value": float(item[1])})
                except (TypeError, ValueError):
                    pass
        if not points:
            continue
        entry = {
            "id": f"{instance}_{spec['suffix']}" if instance else spec['suffix'],
            "name": spec['suffix'],
            "unit": spec["unit"],
            "instance": instance,
            "points": points,
        }
        results.append(entry)
    if limit is not None and isinstance(results, list):
        return results[:limit]
    return results
