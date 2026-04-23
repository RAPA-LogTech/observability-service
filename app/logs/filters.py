from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.observability_service import _opensearch_search, _safe_level, get_settings

router = APIRouter()


@router.get("/filters")
async def get_log_filters() -> dict:
    settings = get_settings()
    app_aggs = {
        "services": {"terms": {"field": "resource.service.name.keyword", "size": 100}},
        "envs": {"terms": {"field": "resource.deployment.environment.keyword", "size": 20}},
        "levels_severityText": {"terms": {"field": "severityText.keyword", "size": 10}},
        "levels_severity_text": {"terms": {"field": "severity.text.keyword", "size": 10}},
        "levels_level": {"terms": {"field": "level.keyword", "size": 10}},
        "hosts": {"terms": {"field": "resource.host.name.keyword", "size": 100}},
    }
    app_result = _opensearch_search(
        settings,
        getattr(settings, "opensearch_app_logs_index", "logs-app"),
        {"size": 0, "aggs": app_aggs},
    )
    host_aggs = {
        "envs": {"terms": {"field": "resource.deployment.environment.keyword", "size": 20}},
        "levels_severityText": {"terms": {"field": "severityText.keyword", "size": 10}},
        "levels_severity_text": {"terms": {"field": "severity.text.keyword", "size": 10}},
        "levels_level": {"terms": {"field": "level.keyword", "size": 10}},
        "hosts": {"terms": {"field": "resource.host.name.keyword", "size": 100}},
    }
    host_result = _opensearch_search(
        settings,
        getattr(settings, "opensearch_host_logs_index", "logs-host"),
        {"size": 0, "aggs": host_aggs},
    )

    def extract_buckets(agg: dict) -> list[str]:
        return [b["key"] for b in agg.get("buckets", []) if b.get("key")]

    def extract_levels(aggs: dict) -> list[str]:
        raw = (
            extract_buckets(aggs.get("levels_severityText", {}))
            + extract_buckets(aggs.get("levels_severity_text", {}))
            + extract_buckets(aggs.get("levels_level", {}))
        )
        normalized = {_safe_level(v) for v in raw}
        normalized.discard(None)
        return sorted(normalized) or ["DEBUG", "ERROR", "INFO", "WARN"]  # type: ignore[arg-type]

    if "__error__" in app_result:
        return JSONResponse(status_code=502, content={"error": app_result["__error__"]})
    if "__error__" in host_result:
        return JSONResponse(status_code=502, content={"error": host_result["__error__"]})

    app_aggs_result = app_result.get("aggregations", {})
    host_aggs_result = host_result.get("aggregations", {})

    return {
        "logs-app": {
            "services": sorted(set(extract_buckets(app_aggs_result.get("services", {}))), key=str),
            "envs": sorted(set(extract_buckets(app_aggs_result.get("envs", {}))), key=str),
            "levels": extract_levels(app_aggs_result),
            "hosts": sorted(set(extract_buckets(app_aggs_result.get("hosts", {}))), key=str),
        },
        "logs-host": {
            "envs": sorted(set(extract_buckets(host_aggs_result.get("envs", {}))), key=str),
            "levels": extract_levels(host_aggs_result),
            "hosts": sorted(set(extract_buckets(host_aggs_result.get("hosts", {}))), key=str),
        },
    }
