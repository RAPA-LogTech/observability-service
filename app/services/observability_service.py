from __future__ import annotations

import base64
import json
import logging
import ssl
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..core.config import Settings, get_settings

# Use uvicorn's logger so info logs are visible in foreground server output.
logger = logging.getLogger("uvicorn.error")


def _normalize_amp_endpoint_for_query(endpoint: str) -> str:
    base = endpoint.strip().rstrip("/")
    if not base:
        return base

    # Accept common AMP endpoint forms and normalize to workspace base URL.
    # e.g. .../workspaces/<id>/api/v1/remote_write -> .../workspaces/<id>
    suffixes = (
        "/api/v1/remote_write",
        "/api/v1/query_range",
        "/api/v1/query",
        "/api/v1",
    )
    for suffix in suffixes:
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def _is_real_mode(settings: Settings) -> bool:
    mode = settings.data_source_mode.strip().lower()
    if mode == "real_only":
        return True
    if mode == "mock":
        return False
    # auto
    return bool(settings.opensearch_url or settings.amp_endpoint)


def _safe_env(value: str | None) -> str:
    candidate = (value or "prod").lower()
    if candidate in {"prod", "staging", "dev"}:
        return candidate
    return "prod"


def _safe_level(value: str | None) -> str:
    candidate = (value or "INFO").upper()
    if candidate in {"INFO", "WARN", "ERROR", "DEBUG"}:
        return candidate
    return "INFO"


def _safe_status(value: str | None) -> str:
    candidate = (value or "ok").lower()
    if candidate in {"ok", "slow", "error"}:
        return candidate
    return "ok"


def _opensearch_auth(settings: Settings) -> tuple[str, str] | None:
    if settings.opensearch_username and settings.opensearch_password:
        return (settings.opensearch_username, settings.opensearch_password)
    # TEMP DEBUG FALLBACK: remove after env loading issue is resolved.
    logger.warning("Using hardcoded OpenSearch credentials fallback for debugging")
    return ("admin", "SDdfgDG1234!")
    return None


def _opensearch_headers(settings: Settings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.opensearch_api_key:
        headers["Authorization"] = f"ApiKey {settings.opensearch_api_key}"
    return headers


def _extract_nested(source: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        # Support flattened keys containing dots (e.g. "resource.attributes.service@name").
        if path in source and source[path] is not None:
            return source[path]

        current: Any = source
        ok = True
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                ok = False
                break
            current = current[key]
        if ok and current is not None:
            return current
    return None


def _normalize_unix_timestamp(value: Any) -> str | None:
    """Normalize seconds/ms/us/ns epoch values into ISO8601 UTC string."""
    raw: float
    if isinstance(value, (int, float)):
        raw = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            raw = float(stripped)
        except ValueError:
            return None
    else:
        return None

    abs_raw = abs(raw)
    if abs_raw >= 1e17:
        seconds = raw / 1e9  # nanoseconds
    elif abs_raw >= 1e14:
        seconds = raw / 1e6  # microseconds
    elif abs_raw >= 1e11:
        seconds = raw / 1e3  # milliseconds
    else:
        seconds = raw  # seconds

    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))
    except (OverflowError, OSError, ValueError):
        return None


def _extract_log_timestamp(source: dict[str, Any], doc: dict[str, Any]) -> str:
    timestamp_paths = [
        "time",
        "@timestamp",
        "timestamp",
        "observedTimestamp",
        "event.time",
        "event.created",
        "log.time",
        "timeUnixNano",
        "time_unix_nano",
        "observedTimeUnixNano",
    ]
    candidates: list[Any] = []
    for path in timestamp_paths:
        value = _extract_nested(source, path)
        if value is not None:
            candidates.append(value)

    sort_values = doc.get("sort") if isinstance(doc, dict) else None
    if isinstance(sort_values, list) and sort_values:
        candidates.append(sort_values[0])

    for candidate in candidates:
        if candidate is None:
            continue

        if isinstance(candidate, str):
            stripped = candidate.strip()
            if not stripped:
                continue

            normalized = _normalize_unix_timestamp(stripped)
            if normalized:
                return normalized
            # ISO8601/Zulu-like string values should pass through as-is.
            if "T" in stripped or stripped.endswith("Z"):
                return stripped
            continue

        normalized = _normalize_unix_timestamp(candidate)
        if normalized:
            return normalized

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _opensearch_search(settings: Settings, index: str, body: dict[str, Any]) -> dict[str, Any]:
    if not settings.opensearch_url:
        return {"__error__": "OPENSEARCH_URL is not configured", "__status__": 503}

    url = f"{settings.opensearch_url.rstrip('/')}/{index}/_search"
    logger.info("OpenSearch request URL: %s", url)
    headers = _opensearch_headers(settings)
    auth = _opensearch_auth(settings)
    if auth:
        logger.info(
            "OpenSearch auth: username=%s password=%s",
            auth[0],
            auth[1],
        )
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    elif settings.opensearch_api_key:
        logger.info("OpenSearch auth: api_key is set")
    else:
        logger.info("OpenSearch auth: no credentials configured")

    request = Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    ssl_context: ssl.SSLContext | None = None
    if url.lower().startswith("https://"):
        if settings.opensearch_verify_tls:
            ssl_context = ssl.create_default_context()
        else:
            # Useful for local SSH tunnel testing (e.g. https://localhost:9200).
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

    try:
        with urlopen(
            request,
            timeout=settings.opensearch_timeout_seconds,
            context=ssl_context,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return {
            "__error__": f"OpenSearch request failed: HTTP {exc.code}",
            "__status__": int(exc.code),
        }
    except URLError as exc:
        reason = getattr(exc, "reason", "connection error")
        return {
            "__error__": f"OpenSearch request failed: {reason}",
            "__status__": 502,
        }
    except TimeoutError:
        return {"__error__": "OpenSearch request timed out", "__status__": 504}
    except ValueError:
        return {"__error__": "OpenSearch response is not valid JSON", "__status__": 502}


def _amp_query_range(
    settings: Settings,
    query: str,
    start_ts: int,
    end_ts: int,
    step_seconds: int,
) -> list[dict[str, Any]]:
    if not settings.amp_endpoint:
        return [{"__error__": "AMP endpoint is not configured", "__status__": 503}]

    workspace_base = _normalize_amp_endpoint_for_query(settings.amp_endpoint)
    url = f"{workspace_base}/api/v1/query_range"

    params = {
        "query": query,
        "start": str(start_ts),
        "end": str(end_ts),
        "step": str(step_seconds),
    }
    query_string = urlencode(params)
    full_url = f"{url}?{query_string}"
    logger.info("AMP request URL: %s", full_url)
    request = Request(url=full_url, method="GET")

    try:
        with urlopen(request, timeout=settings.amp_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            result = payload.get("data", {}).get("result", [])
            return result if isinstance(result, list) else []
    except HTTPError as exc:
        return [{"__error__": f"AMP request failed: HTTP {exc.code}", "__status__": int(exc.code)}]
    except URLError as exc:
        reason = getattr(exc, "reason", "connection error")
        return [{"__error__": f"AMP request failed: {reason}", "__status__": 502}]
    except TimeoutError:
        return [{"__error__": "AMP request timed out", "__status__": 504}]
    except ValueError:
        return [{"__error__": "AMP response is not valid JSON", "__status__": 502}]


def _promql_points(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not series:
        return []

    values = series[0].get("values", [])
    points: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, list) or len(item) != 2:
            continue
        ts, value = item
        try:
            points.append({"ts": int(float(ts) * 1000), "value": float(value)})
        except (TypeError, ValueError):
            continue
    return points


def get_data_source_name() -> str:
    settings = get_settings()
    if not _is_real_mode(settings):
        return "none"
    if settings.opensearch_url and settings.amp_endpoint:
        return "opensearch+amp"
    if settings.opensearch_url:
        return "opensearch"
    if settings.amp_endpoint:
        return "amp"
    return "none"


def _opensearch_health_check(settings: Settings) -> dict[str, Any]:
    if not settings.opensearch_url:
        return {"configured": False, "ok": False, "error": "OPENSEARCH_URL is not configured"}

    url = settings.opensearch_url.rstrip("/")
    headers: dict[str, str] = {}
    auth = _opensearch_auth(settings)
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    elif settings.opensearch_api_key:
        headers["Authorization"] = f"ApiKey {settings.opensearch_api_key}"

    request = Request(url=url, headers=headers, method="GET")

    ssl_context: ssl.SSLContext | None = None
    if url.lower().startswith("https://"):
        if settings.opensearch_verify_tls:
            ssl_context = ssl.create_default_context()
        else:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

    try:
        with urlopen(
            request,
            timeout=settings.opensearch_timeout_seconds,
            context=ssl_context,
        ) as response:
            return {
                "configured": True,
                "ok": True,
                "url": url,
                "http_status": getattr(response, "status", 200),
            }
    except HTTPError as exc:
        return {
            "configured": True,
            "ok": False,
            "url": url,
            "http_status": int(exc.code),
            "error": f"HTTP {exc.code}",
        }
    except URLError as exc:
        reason = getattr(exc, "reason", "connection error")
        return {"configured": True, "ok": False, "url": url, "error": str(reason)}
    except TimeoutError:
        return {"configured": True, "ok": False, "url": url, "error": "timeout"}


def _amp_health_check(settings: Settings) -> dict[str, Any]:
    if not settings.amp_endpoint:
        return {"configured": False, "ok": False, "error": "AMP endpoint is not configured"}

    workspace_base = _normalize_amp_endpoint_for_query(settings.amp_endpoint)
    base_url = f"{workspace_base}/api/v1/query"
    query_string = urlencode({"query": "1", "time": str(int(time.time()))})
    url = f"{base_url}?{query_string}"
    request = Request(url=url, method="GET")

    try:
        with urlopen(request, timeout=settings.amp_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            status = payload.get("status")
            return {
                "configured": True,
                "ok": status == "success",
                "url": url,
                "http_status": getattr(response, "status", 200),
                "response_status": status,
            }
    except HTTPError as exc:
        return {
            "configured": True,
            "ok": False,
            "url": url,
            "http_status": int(exc.code),
            "error": f"HTTP {exc.code}",
        }
    except URLError as exc:
        reason = getattr(exc, "reason", "connection error")
        return {"configured": True, "ok": False, "url": url, "error": str(reason)}
    except TimeoutError:
        return {"configured": True, "ok": False, "url": url, "error": "timeout"}
    except ValueError:
        return {"configured": True, "ok": False, "url": url, "error": "invalid json"}


def get_dependency_health() -> dict[str, Any]:
    settings = get_settings()
    opensearch = _opensearch_health_check(settings)
    amp = _amp_health_check(settings)

    return {
        "opensearch": opensearch,
        "amp": amp,
        "all_ok": bool(opensearch.get("ok") and amp.get("ok")),
    }


def list_logs(
    service: str | None = None,
    level: str | None = None,
    env: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    settings = get_settings()
    if not _is_real_mode(settings):
        return {"logs": [], "total": 0}
    if not settings.opensearch_url:
        return {
            "logs": [],
            "total": 0,
            "__error__": "DATA_SOURCE_MODE is real but OPENSEARCH_URL is not configured",
            "__status__": 503,
        }

    filters: list[dict[str, Any]] = []
    if service:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"service.keyword": service}},
                        {"term": {"service.name.keyword": service}},
                        {"term": {"resource.attributes.service@name.keyword": service}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if level:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"level.keyword": level.upper()}},
                        {"term": {"severityText.keyword": level.upper()}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if env:
        filters.append({"term": {"env.keyword": env}})

    body: dict[str, Any] = {
        "from": max(0, offset),
        "size": max(1, min(limit, 1000)),
        "sort": [
            {"time": {"order": "desc", "unmapped_type": "date"}},
            {"@timestamp": {"order": "desc", "unmapped_type": "date"}},
            {"timestamp": {"order": "desc", "unmapped_type": "date"}},
            {"observedTimestamp": {"order": "desc", "unmapped_type": "date"}},
        ],
        "query": {"bool": {"filter": filters}},
    }

    result = _opensearch_search(settings, settings.opensearch_logs_index, body)
    if "__error__" in result:
        return {
            "logs": [],
            "total": 0,
            "__error__": str(result.get("__error__")),
            "__status__": int(result.get("__status__", 502)),
        }

    hits = result.get("hits", {})
    docs = hits.get("hits", []) if isinstance(hits, dict) else []

    total_value: int
    total_obj = hits.get("total", 0) if isinstance(hits, dict) else 0
    if isinstance(total_obj, dict):
        total_value = int(total_obj.get("value", 0))
    else:
        total_value = int(total_obj) if isinstance(total_obj, int) else 0

    logs: list[dict[str, Any]] = []
    for doc in docs:
        source = doc.get("_source", {}) if isinstance(doc, dict) else {}
        if not isinstance(source, dict):
            continue

        metadata_obj = source.get("metadata")
        tags_obj = source.get("tags")
        metadata: dict[str, Any] = metadata_obj if isinstance(metadata_obj, dict) else {}
        tags: dict[str, Any] = tags_obj if isinstance(tags_obj, dict) else {}

        message = _extract_nested(source, "message", "log", "body")
        logs.append(
            {
                "id": str(doc.get("_id") or _extract_nested(source, "id") or f"log-{len(logs)+1}"),
                "timestamp": _extract_log_timestamp(source, doc),
                "service": str(
                    _extract_nested(
                        source,
                        "service.name",
                        "service",
                        "resource.service.name",
                        "resource.attributes.service@name",
                        "kubernetes.labels.app",
                    )
                    or "unknown",
                ),
                "env": _safe_env(str(_extract_nested(source, "env", "environment") or "prod")),
                "level": _safe_level(
                    str(
                        _extract_nested(
                            source,
                            "level",
                            "severity",
                            "severity_text",
                            "severityText",
                        )
                        or "INFO"
                    )
                ),
                "message": str(message or ""),
                "metadata": metadata,
                "tags": {k: str(v) for k, v in tags.items()},
            }
        )

    return {"logs": logs, "total": max(total_value, len(logs))}


def list_metrics(service: str | None = None) -> list[dict] | dict[str, Any]:
    settings = get_settings()
    if not _is_real_mode(settings):
        return []
    if not settings.amp_endpoint:
        return {
            "__error__": "DATA_SOURCE_MODE is real but AMP_ENDPOINT is not configured",
            "__status__": 503,
        }

    target_service = service or settings.amp_default_service
    now = int(time.time())
    start = now - 3600
    step = max(15, settings.amp_step_seconds)

    metric_specs = [
        {
            "id": "metric-error-rate",
            "name": "Error Rate",
            "unit": "%",
            "color": "#EF4444",
            "query": settings.amp_error_rate_query,
        },
        {
            "id": "metric-latency-p95",
            "name": "Latency P95",
            "unit": "ms",
            "color": "#3B82F6",
            "query": settings.amp_latency_p95_query,
        },
        {
            "id": "metric-throughput",
            "name": "Throughput",
            "unit": "req/s",
            "color": "#10B981",
            "query": settings.amp_throughput_query,
        },
    ]

    series_list: list[dict[str, Any]] = []
    for spec in metric_specs:
        query = spec["query"].replace("$service", target_service)
        result = _amp_query_range(settings, query, start, now, step)
        if result and isinstance(result[0], dict) and "__error__" in result[0]:
            return {
                "__error__": str(result[0].get("__error__")),
                "__status__": int(result[0].get("__status__", 502)),
            }

        points = _promql_points(result)
        if not points:
            continue

        series_list.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "unit": spec["unit"],
                "service": target_service,
                "points": points,
                "color": spec["color"],
            }
        )

    return series_list


def list_traces(
    service: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    settings = get_settings()
    if not _is_real_mode(settings):
        return {"traces": [], "total": 0}
    if not settings.opensearch_url:
        return {
            "traces": [],
            "total": 0,
            "__error__": "DATA_SOURCE_MODE is real but OPENSEARCH_URL is not configured",
            "__status__": 503,
        }
    if not settings.opensearch_traces_index:
        return {
            "traces": [],
            "total": 0,
            "__error__": "OPENSEARCH_TRACES_INDEX is not configured",
            "__status__": 503,
        }

    filters: list[dict[str, Any]] = []
    if service:
        filters.append({"term": {"service.keyword": service}})

    body: dict[str, Any] = {
        "from": max(0, offset),
        "size": max(1, min(limit, 500)),
        "sort": [{"startTime": {"order": "desc", "unmapped_type": "long"}}],
        "query": {"bool": {"filter": filters}},
    }
    result = _opensearch_search(settings, settings.opensearch_traces_index, body)
    if "__error__" in result:
        return {
            "traces": [],
            "total": 0,
            "__error__": str(result.get("__error__")),
            "__status__": int(result.get("__status__", 502)),
        }

    hits = result.get("hits", {})
    docs = hits.get("hits", []) if isinstance(hits, dict) else []

    traces: list[dict[str, Any]] = []
    for doc in docs:
        source = doc.get("_source", {}) if isinstance(doc, dict) else {}
        if not isinstance(source, dict):
            continue

        trace_id = str(_extract_nested(source, "id", "traceId") or doc.get("_id") or "")
        if not trace_id:
            continue

        spans_obj = source.get("spans")
        spans: list[Any] = spans_obj if isinstance(spans_obj, list) else []
        normalized_spans: list[dict[str, Any]] = []
        for idx, span in enumerate(spans):
            if not isinstance(span, dict):
                continue
            normalized_spans.append(
                {
                    "id": str(span.get("id") or f"{trace_id}-span-{idx+1}"),
                    "traceId": trace_id,
                    "parentSpanId": span.get("parentSpanId"),
                    "service": str(span.get("service") or source.get("service") or "unknown"),
                    "operation": str(span.get("operation") or span.get("name") or "operation"),
                    "startTime": int(
                        span.get("startTime") or source.get("startTime") or int(time.time() * 1000)
                    ),
                    "duration": int(span.get("duration") or 0),
                    "status": _safe_status(str(span.get("status") or source.get("status") or "ok")),
                    "tags": span.get("tags") if isinstance(span.get("tags"), dict) else {},
                }
            )

        status_value = _safe_status(str(source.get("status") or "ok"))
        trace_item = {
            "id": trace_id,
            "service": str(
                _extract_nested(source, "service.name", "service", "resource.service.name")
                or "unknown"
            ),
            "operation": str(_extract_nested(source, "operation", "name") or "operation"),
            "startTime": int(source.get("startTime") or int(time.time() * 1000)),
            "duration": int(source.get("duration") or 0),
            "status": status_value,
            "status_code": int(source.get("status_code") or (200 if status_value == "ok" else 500)),
            "spans": normalized_spans,
            "tags": source.get("tags") if isinstance(source.get("tags"), dict) else {},
        }
        traces.append(trace_item)

    if status:
        traces = [item for item in traces if item.get("status") == status]

    return {"traces": traces, "total": len(traces)}


def get_trace_detail(trace_id: str) -> dict | None:
    traces = list_traces(limit=200, offset=0).get("traces", [])
    for trace in traces:
        if str(trace.get("id")) == trace_id:
            return trace
    return None
