from __future__ import annotations

import base64
import json
import logging
import re
import ssl
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from ..core.config import Settings, get_settings

# Use uvicorn's logger so info logs are visible in foreground server output.
logger = logging.getLogger("uvicorn.error")


def _normalize_amp_endpoint_for_query(endpoint: str) -> str:
    base = endpoint.strip().rstrip("/")
    if not base:
        return base

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
    logger.error("OpenSearch credentials are not set in environment variables!")
    return None


def _opensearch_headers(settings: Settings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.opensearch_api_key:
        headers["Authorization"] = f"ApiKey {settings.opensearch_api_key}"
    return headers


def _extract_nested(source: dict[str, Any], *paths: str) -> Any:
    for path in paths:
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


def _normalize_to_millis(value: Any) -> int | None:
    """Normalize seconds/ms/us/ns epoch values or ISO8601 strings into Unix milliseconds."""
    # ISO8601 문자열 처리
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        # ISO8601 형식인 경우 파싱
        if "T" in stripped or ("-" in stripped and ":" in stripped):
            try:
                from datetime import datetime
                dt_str = stripped.rstrip("Z")
                # 소수점 이하 6자리 초과(나노초 등) → 마이크로초로 truncate
                if "." in dt_str:
                    int_part, frac_part = dt_str.split(".", 1)
                    dt_str = f"{int_part}.{frac_part[:6]}"
                    dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f")
                else:
                    dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
                return int(dt.timestamp() * 1000)
            except (ValueError, ImportError):
                pass
            try:
                raw = float(stripped)
            except ValueError:
                return None
        else:
            try:
                raw = float(stripped)
            except ValueError:
                return None
    elif isinstance(value, (int, float)):
        raw = float(value)
    else:
        return None

    abs_raw = abs(raw)
    if abs_raw >= 1e17:
        return int(raw / 1e9)  # ns → ms
    elif abs_raw >= 1e14:
        return int(raw / 1e6)  # us → ms
    elif abs_raw >= 1e11:
        return int(raw / 1e3)  # s → ms
    elif abs_raw < 1e10:
        return int(raw * 1000)  # s → ms
    else:
        return int(raw)  # 이미 ms


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
        seconds = raw / 1e9
    elif abs_raw >= 1e14:
        seconds = raw / 1e6
    elif abs_raw >= 1e11:
        seconds = raw / 1e3
    else:
        seconds = raw

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
            if "T" in stripped or stripped.endswith("Z"):
                return stripped
            continue

        normalized = _normalize_unix_timestamp(candidate)
        if normalized:
            return normalized

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _make_sigv4_request(method: str, url: str) -> Request:
    """
    AWS SigV4 인증 헤더를 붙인 urllib.request.Request 객체 생성
    컨테이너 환경에서 IMDSv2 hop limit 문제를 우회하기 위해
    환경변수 자격증명을 우선 사용하고, 없으면 IMDSv2로 fallback
    """
    import os

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-northeast-2"

    # 환경변수에 자격증명이 있으면 직접 사용 (컨테이너 환경 우선)
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    session_token = os.environ.get("AWS_SESSION_TOKEN")

    if access_key and secret_key:
        from botocore.credentials import Credentials, RefreshableCredentials
        creds = Credentials(
            access_key=access_key,
            secret_key=secret_key,
            token=session_token,
        )
    else:
        # EC2 IAM Role (IMDSv2) — hop limit >= 2 필요
        session = boto3.Session(region_name=region)
        resolved = session.get_credentials()
        if resolved is None:
            raise RuntimeError("AWS credentials not found. Set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or ensure EC2 IMDSv2 hop limit >= 2.")
        creds = resolved.get_frozen_credentials()

    aws_req = AWSRequest(method=method, url=url)
    SigV4Auth(creds, "aps", region).add_auth(aws_req)
    headers = dict(aws_req.headers)
    logger.info(f"[SIGV4 DEBUG] url={url} region={region} headers={headers}")
    return Request(url=url, method=method, headers=headers)


def _opensearch_search(settings: Settings, index: str, body: dict[str, Any]) -> dict[str, Any]:
    if not settings.opensearch_url:
        return {"__error__": "OPENSEARCH_URL is not configured", "__status__": 503}

    url = f"{settings.opensearch_url.rstrip('/')}/{index}/_search"
    logger.info("OpenSearch request URL: %s", url)
    headers = _opensearch_headers(settings)
    auth = _opensearch_auth(settings)
    if auth:
        logger.info("OpenSearch auth: username=%s password=%s", auth[0], auth[1])
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
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

    try:
        with urlopen(request, timeout=settings.opensearch_timeout_seconds, context=ssl_context) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return {"__error__": f"OpenSearch request failed: HTTP {exc.code}", "__status__": int(exc.code)}
    except URLError as exc:
        reason = getattr(exc, "reason", "connection error")
        return {"__error__": f"OpenSearch request failed: {reason}", "__status__": 502}
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
    full_url = f"{url}?{urlencode(params, quote_via=quote)}"
    logger.info("AMP request URL: %s", full_url)

    request = _make_sigv4_request("GET", full_url)

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


def _amp_instant_query(settings: Settings, query: str) -> list[dict[str, Any]]:
    """AMP instant query → 현재 시점 값만 반환"""
    if not settings.amp_endpoint:
        return []
    workspace_base = _normalize_amp_endpoint_for_query(settings.amp_endpoint)
    url = f"{workspace_base}/api/v1/query?{urlencode({'query': query, 'time': str(int(time.time()))}, quote_via=quote)}"
    try:
        request = _make_sigv4_request("GET", url)
        with urlopen(request, timeout=settings.amp_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("data", {}).get("result", [])
    except Exception:
        return []


def get_latest_metric_points() -> list[dict[str, Any]]:
    """스트리밍용: 각 서비스×메트릭의 현재값만 instant query로 조회 (병렬)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    settings = get_settings()
    if not _is_real_mode(settings) or not settings.amp_endpoint:
        return []

    services = _amp_list_services(settings)
    if not services:
        return []

    metric_specs = [
        {"suffix": "request_rate", "unit": "req/s",  "query": settings.amp_throughput_query},
        {"suffix": "error_rate",   "unit": "%",       "query": settings.amp_error_rate_query},
        {"suffix": "latency_p95",  "unit": "ms",      "query": settings.amp_latency_p95_query},
        {"suffix": "cpu_usage",    "unit": "%",       "query": settings.amp_cpu_query},
        {"suffix": "memory_usage", "unit": "%",       "query": settings.amp_memory_query},
    ]

    now_ms = int(time.time() * 1000)
    tasks = [
        (svc, spec)
        for svc in services
        for spec in metric_specs
    ]

    def _fetch(svc: str, spec: dict) -> dict[str, Any] | None:
        query = spec["query"].replace("$service", svc)
        result = _amp_instant_query(settings, query)
        if not result:
            return None
        try:
            value = float(result[0]["value"][1])
        except (KeyError, IndexError, ValueError, TypeError):
            return None
        return {"id": f"{svc}_{spec['suffix']}", "ts": now_ms, "value": value}

    points: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(tasks), 10)) as executor:
        futures = {executor.submit(_fetch, svc, spec): (svc, spec) for svc, spec in tasks}
        for future in as_completed(futures):
            result = future.result()
            if result:
                points.append(result)
    return points


def list_service_health() -> list[dict[str, Any]]:
    """서비스별 에러율 + 환경(dev/prod) 목록 반환.
    _amp_list_services와 동일한 서비스 목록 기준.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    settings = get_settings()
    if not _is_real_mode(settings) or not settings.amp_endpoint:
        return []

    jobs = _amp_list_jobs(settings)
    if not jobs:
        return []

    # job → {service: {envs, jobs}} — _amp_list_services와 동일한 svc 추출 로직
    service_meta: dict[str, dict[str, Any]] = {}
    for job in jobs:
        svc = job.split("/")[-1] if "/" in job else job
        env = _parse_env_from_job(job)
        if svc not in service_meta:
            service_meta[svc] = {"envs": set(), "jobs": []}
        service_meta[svc]["envs"].add(env)
        service_meta[svc]["jobs"].append(job)

    def _fetch_error_rate(svc: str, svc_jobs: list[str]) -> tuple[str, float]:
        job_pattern = "|".join(re.escape(j) for j in svc_jobs)
        query = f'app_http_server_error_ratio_5m{{job=~"{job_pattern}"}}'
        result = _amp_instant_query(settings, query)
        try:
            value = float(result[0]["value"][1]) if result else 0.0
        except (KeyError, IndexError, ValueError, TypeError):
            value = 0.0
        return svc, value

    error_rates: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=min(len(service_meta), 10)) as executor:
        futures = {
            executor.submit(_fetch_error_rate, svc, meta["jobs"]): svc
            for svc, meta in service_meta.items()
        }
        for future in as_completed(futures):
            svc, rate = future.result()
            error_rates[svc] = rate

    return [
        {
            "service": svc,
            "envs": sorted(service_meta[svc]["envs"]),
            "error_rate": error_rates.get(svc, 0.0),
        }
        for svc in sorted(service_meta)
    ]


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
        with urlopen(request, timeout=settings.opensearch_timeout_seconds, context=ssl_context) as response:
            return {"configured": True, "ok": True, "url": url, "http_status": getattr(response, "status", 200)}
    except HTTPError as exc:
        return {"configured": True, "ok": False, "url": url, "http_status": int(exc.code), "error": f"HTTP {exc.code}"}
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

    request = _make_sigv4_request("GET", url)

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
        return {"configured": True, "ok": False, "url": url, "http_status": int(exc.code), "error": f"HTTP {exc.code}"}
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
    cluster: str | None = None,
    log_source: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    custom_tags: dict | None = None,
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
                        {"term": {"resource.service.name.keyword": service}},
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
                        {"term": {"severity.text.keyword": level.upper()}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if env:
        filters.append({
            "bool": {
                "should": [
                    {"term": {"env.keyword": env}},
                    {"term": {"resource.deployment.environment.keyword": env}},
                ],
                "minimum_should_match": 1,
            }
        })
    if cluster:
        filters.append({"term": {"cluster.keyword": cluster}})
    if start_time or end_time:
        range_filter = {}
        if start_time:
            range_filter["gte"] = start_time
        if end_time:
            range_filter["lte"] = end_time
        filters.append({"range": {"@timestamp": range_filter}})
    if custom_tags and isinstance(custom_tags, dict):
        for k, v in custom_tags.items():
            if isinstance(v, list):
                filters.append({"terms": {f"tags.{k}.keyword": v}})
            else:
                filters.append({"term": {f"tags.{k}.keyword": v}})

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

    result = _opensearch_search(settings, settings.opensearch_logs_index if not log_source else f"logs-{log_source}", body)
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

        # 진단용: service 추출이 안될 때 로그 출력
        service_val = (
            _extract_nested(
                source,
                "service.name",
                "service",
                "resource.service.name",
                "resource.attributes.service@name",
                "kubernetes.labels.app",
            )
            or source.get("resource", {}).get("service.name")
            or "unknown"
        )

        trace_id = (
            _extract_nested(source, "traceId")
            or source.get("traceId")
            or source.get("resource", {}).get("traceId")
            or ""
        )
        logs.append(
            {
                "id": str(doc.get("_id") or _extract_nested(source, "id") or f"log-{len(logs)+1}"),
                "timestamp": _extract_log_timestamp(source, doc),
                "source": doc.get("_index", ""),  # 로그 소스 (logs-app, logs-host 등)
                "service": str(service_val),
                "traceId": str(trace_id),
                "env": _safe_env(str(_extract_nested(source, "env", "environment") or "prod")),
                "level": _safe_level(
                    str(
                        _extract_nested(source, "level", "severity", "severity_text", "severityText")
                        or "INFO"
                    )
                ),
                "message": str(message or ""),
                "metadata": metadata,
                "tags": {k: str(v) for k, v in tags.items()},
            }
        )

    return {"logs": logs, "total": max(total_value, len(logs))}


def _amp_list_jobs(settings: Settings) -> list[str]:
    """AMP job label 원본 목록 반환"""
    if not settings.amp_endpoint:
        return []
    workspace_base = _normalize_amp_endpoint_for_query(settings.amp_endpoint)
    url = f"{workspace_base}/api/v1/label/job/values"
    try:
        request = _make_sigv4_request("GET", url)
        with urlopen(request, timeout=settings.amp_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("data", [])
    except Exception:
        return []


def _parse_env_from_job(job: str) -> str:
    parts = job.split("/")
    candidate = parts[0].lower() if len(parts) > 1 else parts[0].lower()
    for token in (candidate, job.lower()):
        if "prod" in token:
            return "prod"
        if "dev" in token or "development" in token:
            return "dev"
        if "staging" in token or "stage" in token:
            return "staging"
    return "prod"


def _amp_list_services(settings: Settings) -> list[str]:
    jobs = _amp_list_jobs(settings)
    seen: set[str] = set()
    services: list[str] = []
    for job in jobs:
        svc = job.split("/")[-1] if "/" in job else job
        if svc not in seen:
            seen.add(svc)
            services.append(svc)
    return services


def list_metrics(service: str | None = None, start: int | None = None, end: int | None = None) -> list[dict] | dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    settings = get_settings()
    if not _is_real_mode(settings):
        return []
    if not settings.amp_endpoint:
        return {"__error__": "DATA_SOURCE_MODE is real but AMP_ENDPOINT is not configured", "__status__": 503}

    services = [service] if service else _amp_list_services(settings)
    if not services:
        return []

    now = int(time.time())
    end = end or now
    start = start or (end - 60)
    step = max(60, settings.amp_step_seconds)

    metric_specs = [
        {"suffix": "request_rate", "unit": "req/s",  "query": settings.amp_throughput_query},
        {"suffix": "error_rate",   "unit": "%",       "query": settings.amp_error_rate_query},
        {"suffix": "latency_p95",  "unit": "ms",      "query": settings.amp_latency_p95_query},
        {"suffix": "cpu_usage",    "unit": "%",       "query": settings.amp_cpu_query},
        {"suffix": "memory_usage", "unit": "%",       "query": settings.amp_memory_query},
    ]

    tasks = [(svc, spec) for svc in services for spec in metric_specs]

    def _fetch(svc: str, spec: dict) -> tuple[str, dict, list]:
        query = spec["query"].replace("$service", svc)
        return svc, spec, _amp_query_range(settings, query, start, end, step)

    results: dict[tuple, list] = {}
    first_error: dict[str, Any] | None = None

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
        return {"__error__": str(first_error.get("__error__")), "__status__": int(first_error.get("__status__", 502))}

    series_list: list[dict[str, Any]] = []
    for svc, spec in tasks:
        result = results.get((svc, spec["suffix"]), [])
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
        series_list.append({
            "id": f"{svc}_{spec['suffix']}",
            "name": f"{svc}_{spec['suffix']}",
            "unit": spec["unit"],
            "service": svc,
            "points": points,
        })

    return series_list


def _parse_span_doc(source: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any] | None:
    """OpenSearch span document를 정규화된 span dict로 변환."""
    trace_id = str(source.get("traceId") or "")
    if not trace_id:
        return None

    span_id = str(source.get("spanId") or doc.get("_id") or "")
    parent_span_id = source.get("parentSpanId") or ""

    resource = source.get("resource")
    service_name = "unknown"
    if isinstance(resource, dict):
        # resource dict 안에 "service.name" dot-key가 있는 경우 (OTel Collector 기본 형식)
        sn = resource.get("service.name")
        if not sn and isinstance(resource.get("service"), dict):
            sn = resource["service"].get("name")
        if sn:
            service_name = str(sn)
    if service_name == "unknown":
        sn = _extract_nested(source, "service.name", "service")
        if sn:
            service_name = str(sn)
    operation = str(source.get("name") or "unknown")
    kind = str(source.get("kind") or "")

    start_ms = _normalize_to_millis(source.get("startTime"))
    end_ms = _normalize_to_millis(source.get("endTime"))
    if start_ms and end_ms and end_ms > start_ms:
        duration = end_ms - start_ms
    else:
        duration = 0
    if not start_ms:
        start_ms = int(time.time() * 1000)

    status_obj = source.get("status")
    status_code_str = "Unset"
    if isinstance(status_obj, dict):
        status_code_str = str(status_obj.get("code") or "Unset")
    elif isinstance(status_obj, str):
        status_code_str = status_obj

    if status_code_str.lower() == "error":
        span_status = "error"
    elif status_code_str.lower() == "ok":
        span_status = "ok"
    else:
        span_status = "ok"

    attrs = source.get("attributes") or {}
    http_status = attrs.get("http.status_code")

    tags: dict[str, Any] = {}
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            if k == "data_stream":
                continue
            tags[k] = v

    resource = source.get("resource")
    if isinstance(resource, dict):
        for k, v in resource.items():
            if k not in ("service.name",) and not isinstance(v, dict):
                tags[f"resource.{k}"] = v

    return {
        "id": span_id,
        "traceId": trace_id,
        "parentSpanId": parent_span_id if parent_span_id else None,
        "service": service_name,
        "operation": operation,
        "kind": kind,
        "startTime": start_ms,
        "duration": duration,
        "status": span_status,
        "httpStatusCode": int(http_status) if http_status is not None else None,
        "tags": tags,
    }


def _group_spans_into_traces(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """span 목록을 traceId별로 그룹핑하여 Trace 객체 목록으로 변환."""
    from collections import defaultdict

    trace_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in spans:
        trace_map[span["traceId"]].append(span)

    traces: list[dict[str, Any]] = []
    for trace_id, trace_spans in trace_map.items():
        sorted_spans = sorted(trace_spans, key=lambda s: s["startTime"])

        root_span = None
        for s in sorted_spans:
            if not s.get("parentSpanId"):
                root_span = s
                break
        if not root_span:
            root_span = sorted_spans[0]

        trace_start = min(s["startTime"] for s in sorted_spans)
        trace_end = max(s["startTime"] + s["duration"] for s in sorted_spans)
        trace_duration = max(trace_end - trace_start, 0)

        has_error = any(s["status"] == "error" for s in sorted_spans)
        http_code = root_span.get("httpStatusCode")
        if http_code is None:
            for s in sorted_spans:
                if s.get("httpStatusCode") is not None:
                    http_code = s["httpStatusCode"]
                    break

        if has_error:
            trace_status = "error"
            if http_code is None:
                http_code = 500
        else:
            trace_status = "ok"
            if http_code is None:
                http_code = 200

        traces.append({
            "id": trace_id,
            "service": root_span["service"],
            "operation": root_span["operation"],
            "startTime": trace_start,
            "duration": trace_duration,
            "status": trace_status,
            "status_code": http_code,
            "spans": sorted_spans,
            "tags": root_span.get("tags", {}),
        })

    traces.sort(key=lambda t: t["startTime"], reverse=True)
    return traces


def list_traces(
    service: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    start_time: int | None = None,
    end_time: int | None = None,
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

    now_ms = int(time.time() * 1000)
    resolved_end = end_time if end_time is not None else now_ms
    resolved_start = start_time if start_time is not None else (resolved_end - 10 * 60 * 1000)

    filters: list[dict[str, Any]] = []
    filters.append({"range": {"startTime": {"gte": resolved_start, "lte": resolved_end}}})
    if service:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"resource.service.name.keyword": service}},
                        {"term": {"resource.service.name": service}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )

    # span 단위 document를 traceId별로 그룹핑하여 조회
    # 최대 limit개 trace를 얻기 위해 충분한 span을 가져옴
    fetch_size = max(1, min(limit * 10, 5000))
    body: dict[str, Any] = {
        "size": fetch_size,
        "sort": [{"startTime": {"order": "desc", "unmapped_type": "keyword"}}],
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

    all_spans: list[dict[str, Any]] = []
    for doc in docs:
        source = doc.get("_source", {}) if isinstance(doc, dict) else {}
        if not isinstance(source, dict):
            continue
        span = _parse_span_doc(source, doc)
        if span:
            all_spans.append(span)

    traces = _group_spans_into_traces(all_spans)

    if status:
        traces = [t for t in traces if t["status"] == status]

    total = len(traces)
    traces = traces[offset:offset + limit]

    return {"traces": traces, "total": total}


def get_trace_detail(trace_id: str) -> dict | None:
    settings = get_settings()
    if not _is_real_mode(settings) or not settings.opensearch_url or not settings.opensearch_traces_index:
        return None

    body: dict[str, Any] = {
        "size": 1000,
        "query": {"term": {"traceId": trace_id}},
        "sort": [{"startTime": {"order": "asc", "unmapped_type": "keyword"}}],
    }
    result = _opensearch_search(settings, settings.opensearch_traces_index, body)
    if "__error__" in result:
        return None

    hits = result.get("hits", {})
    docs = hits.get("hits", []) if isinstance(hits, dict) else []

    spans: list[dict[str, Any]] = []
    for doc in docs:
        source = doc.get("_source", {}) if isinstance(doc, dict) else {}
        if not isinstance(source, dict):
            continue
        span = _parse_span_doc(source, doc)
        if span:
            spans.append(span)

    if not spans:
        return None

    traces = _group_spans_into_traces(spans)
    return traces[0] if traces else None