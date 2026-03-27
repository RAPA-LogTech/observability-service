from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter

from ..services.observability_service import (
    _amp_instant_query,
    _amp_list_jobs,
    _is_real_mode,
    _opensearch_search,
    _parse_env_from_job,
    get_settings,
    list_logs,
)

router = APIRouter(prefix="/v1", tags=["overview"])


def _amp_overview(settings) -> tuple[dict, list[dict]]:
    """AMP에서 서비스별 KPI를 가져온다. 실패 시 빈 결과 반환."""
    jobs = _amp_list_jobs(settings)
    if not jobs:
        return {"error_rate": 0, "latency_p95": 0, "throughput": 0}, []

    svc_meta: dict[str, dict] = {}
    for job in jobs:
        svc = job.split("/")[-1] if "/" in job else job
        env = _parse_env_from_job(job)
        if svc not in svc_meta:
            svc_meta[svc] = {"envs": set(), "jobs": []}
        if env:
            svc_meta[svc]["envs"].add(env)
        svc_meta[svc]["jobs"].append(job)

    def _fetch(svc: str, meta: dict) -> dict:
        job_pat = "|".join(re.escape(j) for j in meta["jobs"])
        queries = {
            "error_rate": f'app_http_server_error_ratio_5m{{job=~"{job_pat}"}}',
            "latency_p95": f'app_http_server_latency_p95_5m{{job=~"{job_pat}"}} * 1000',
            "throughput": f'app_http_server_requests_5m{{job=~"{job_pat}"}}',
        }
        vals: dict[str, float] = {}
        for key, q in queries.items():
            r = _amp_instant_query(settings, q)
            try:
                vals[key] = float(r[0]["value"][1]) if r else 0.0
            except (KeyError, IndexError, ValueError, TypeError):
                vals[key] = 0.0
        return {
            "service": svc,
            "envs": sorted(meta["envs"]),
            "error_rate": vals["error_rate"],
            "latency_p95": vals["latency_p95"],
            "throughput": vals["throughput"],
        }

    services: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(len(svc_meta), 10)) as ex:
        futs = {ex.submit(_fetch, s, m): s for s, m in svc_meta.items()}
        for f in as_completed(futs):
            services.append(f.result())

    services.sort(key=lambda s: s["service"])
    n = len(services)
    kpi = {
        "error_rate": round(sum(s["error_rate"] for s in services) / n, 4) if n else 0,
        "latency_p95": round(sum(s["latency_p95"] for s in services) / n, 2) if n else 0,
        "throughput": round(sum(s["throughput"] for s in services), 2) if n else 0,
    }
    return kpi, services


def _opensearch_overview(settings) -> tuple[dict, list[dict]]:
    """AMP 불가 시 OpenSearch 로그 집계로 서비스 목록 + 에러율 fallback."""
    now = int(time.time() * 1000)
    five_min_ago = now - 5 * 60 * 1000

    body = {
        "size": 0,
        "query": {"range": {"@timestamp": {"gte": five_min_ago, "lte": now}}},
        "aggs": {
            "by_service": {
                "terms": {"field": "resource.service.name.keyword", "size": 50},
                "aggs": {
                    "envs": {"terms": {"field": "resource.deployment.environment.keyword", "size": 10}},
                    "errors": {
                        "filter": {
                            "bool": {
                                "should": [
                                    {"term": {"severity.text.keyword": "ERROR"}},
                                    {"term": {"level.keyword": "ERROR"}},
                                ],
                                "minimum_should_match": 1,
                            }
                        }
                    },
                },
            }
        },
    }

    result = _opensearch_search(settings, settings.opensearch_logs_index, body)
    if "__error__" in result:
        return {"error_rate": 0, "latency_p95": 0, "throughput": 0}, []

    buckets = result.get("aggregations", {}).get("by_service", {}).get("buckets", [])
    services: list[dict] = []
    total_logs = 0
    total_errors = 0

    for b in buckets:
        doc_count = b.get("doc_count", 0)
        err_count = b.get("errors", {}).get("doc_count", 0)
        envs = [e["key"] for e in b.get("envs", {}).get("buckets", [])]
        rate = err_count / doc_count if doc_count > 0 else 0.0
        total_logs += doc_count
        total_errors += err_count
        services.append({
            "service": b["key"],
            "envs": sorted(envs),
            "error_rate": round(rate, 4),
            "latency_p95": 0,
            "throughput": round(doc_count / 300, 2),
        })

    services.sort(key=lambda s: s["service"])
    n = len(services)
    kpi = {
        "error_rate": round(total_errors / total_logs, 4) if total_logs else 0,
        "latency_p95": 0,
        "throughput": round(total_logs / 300, 2) if total_logs else 0,
    }
    return kpi, services


@router.get("/overview")
def get_overview() -> dict:
    settings = get_settings()
    real = _is_real_mode(settings)

    kpi = {"error_rate": 0, "latency_p95": 0, "throughput": 0}
    services: list[dict] = []
    source = "none"

    if real:
        # AMP 우선 시도
        if settings.amp_endpoint:
            kpi, services = _amp_overview(settings)

        # AMP에서 서비스를 못 가져왔으면 OpenSearch fallback
        if not services and settings.opensearch_url:
            kpi, services = _opensearch_overview(settings)
            source = "opensearch"
        else:
            source = "amp"

    # 최근 로그
    log_result = list_logs(limit=5) if real else {"logs": [], "total": 0}
    recent_logs = log_result.get("logs", []) if isinstance(log_result, dict) else []

    return {
        "kpi": kpi,
        "services": services,
        "recent_logs": recent_logs,
        "source": source,
    }
