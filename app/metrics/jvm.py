from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from fastapi import APIRouter, HTTPException
from ..core.config import get_settings
from ..services.observability_service import _is_real_mode, _amp_query_range

router = APIRouter()

@router.get("/jvm")
async def get_jvm_metrics(
    service: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int | None = None,
) -> object:
    settings = get_settings()
    if not _is_real_mode(settings):
        return []
    if not settings.amp_endpoint:
        raise HTTPException(
            status_code=503,
            detail="DATA_SOURCE_MODE is real but AMP_ENDPOINT is not configured",
        )

    now = int(time.time())
    end = end or now
    start = start or (end - 60)
    step = max(60, settings.amp_step_seconds)

    metric_specs = [
        {
            "suffix": "jvm_cpu_utilization_pct_avg_5m",
            "unit": "%",
            "metric": "app_jvm_cpu_utilization_pct_avg_5m",
        },
        {"suffix": "jvm_memory_used_avg_5m", "unit": "MB", "metric": "app_jvm_memory_used_avg_5m"},
        {"suffix": "jvm_gc_count_5m", "unit": "회", "metric": "app_jvm_gc_count_5m"},
        {"suffix": "jvm_gc_duration_p95_5m", "unit": "ms", "metric": "app_jvm_gc_duration_p95_5m"},
    ]

    tasks = metric_specs

    def _build_query(metric_name: str) -> str:
        if not service:
            return metric_name
        # label 이름이 환경별로 다를 수 있어 job/service_name 양쪽을 허용한다.
        return f'{metric_name}{{job=~".*{service}.*"}} or {metric_name}{{service_name="{service}"}}'

    def _fetch(spec: dict) -> tuple[dict, list]:
        query = _build_query(spec["metric"])
        return spec, _amp_query_range(settings, query, start, end, step)

    results: dict[str, list] = {}
    first_error: dict | None = None

    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as executor:
        futures = {executor.submit(_fetch, spec): spec for spec in tasks}
        for future in as_completed(futures):
            spec, result = future.result()
            if result and isinstance(result[0], dict) and "__error__" in result[0]:
                if first_error is None:
                    first_error = result[0]
                continue
            results[spec["suffix"]] = result

    if first_error and not results:
        raise HTTPException(
            status_code=int(first_error.get("__status__", 502)),
            detail=str(first_error.get("__error__")),
        )

    def _extract_service(metric_labels: dict) -> str:
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
        return service or "unknown"

    series_list: list[dict] = []
    for spec in tasks:
        result = results.get(spec["suffix"], [])
        for row in result:
            if not isinstance(row, dict):
                continue
            values = row.get("values", [])
            points = []
            for item in values:
                if isinstance(item, list) and len(item) == 2:
                    try:
                        points.append({"ts": int(float(item[0]) * 1000), "value": float(item[1])})
                    except (TypeError, ValueError):
                        pass
            if not points:
                continue

            metric_labels = row.get("metric", {}) if isinstance(row.get("metric", {}), dict) else {}
            svc = _extract_service(metric_labels)
            series_list.append({
                "id": f"{svc}_{spec['suffix']}",
                "name": f"{svc}_{spec['suffix']}",
                "unit": spec["unit"],
                "service": svc,
                "points": points,
            })

    if limit is not None and isinstance(series_list, list):
        return series_list[:limit]
    return series_list
