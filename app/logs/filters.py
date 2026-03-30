from fastapi import APIRouter
from fastapi.responses import JSONResponse
from ..services.observability_service import _opensearch_search, get_settings

router = APIRouter()

@router.get("/logs/filters")
async def get_log_filters() -> dict:
    settings = get_settings()
    app_aggs = {
        "services": {"terms": {"field": "resource.service.name.keyword", "size": 100}},
        "envs": {"terms": {"field": "resource.deployment.environment.keyword", "size": 20}},
        "levels": {"terms": {"field": "severity.text.keyword", "size": 10}},
        "hosts": {"terms": {"field": "resource.host.name.keyword", "size": 100}},
    }
    app_result = _opensearch_search(settings, getattr(settings, "opensearch_app_logs_index", "logs-app"), {"size": 0, "aggs": app_aggs})
    host_aggs = {
        "envs": {"terms": {"field": "resource.deployment.environment.keyword", "size": 20}},
        "levels": {"terms": {"field": "severity.text.keyword", "size": 10}},
        "hosts": {"terms": {"field": "resource.host.name.keyword", "size": 100}},
    }
    host_result = _opensearch_search(settings, getattr(settings, "opensearch_host_logs_index", "logs-host"), {"size": 0, "aggs": host_aggs})

    def extract_buckets(agg):
        return [b["key"] for b in agg.get("buckets", [])]

    if "__error__" in app_result:
        return JSONResponse(status_code=502, content={"error": app_result["__error__"]})
    if "__error__" in host_result:
        return JSONResponse(status_code=502, content={"error": host_result["__error__"]})

    return {
        "logs-app": {
            "services": sorted(set(extract_buckets(app_result.get("aggregations", {}).get("services", {}))), key=str),
            "envs": sorted(set(extract_buckets(app_result.get("aggregations", {}).get("envs", {}))), key=str),
            "levels": sorted(set(extract_buckets(app_result.get("aggregations", {}).get("levels", {}))), key=str) or ["INFO", "WARN", "ERROR", "DEBUG"],
            "hosts": sorted(set(extract_buckets(app_result.get("aggregations", {}).get("hosts", {}))), key=str),
        },
        "logs-host": {
            "envs": sorted(set(extract_buckets(host_result.get("aggregations", {}).get("envs", {}))), key=str),
            "levels": sorted(set(extract_buckets(host_result.get("aggregations", {}).get("levels", {}))), key=str) or ["INFO", "WARN", "ERROR", "DEBUG"],
            "hosts": sorted(set(extract_buckets(host_result.get("aggregations", {}).get("hosts", {}))), key=str),
        },
    }
