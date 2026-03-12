"""
observability-service
- /health              : 헬스체크
- GET /v1/logs         : 로그 목록 (service, level, limit, offset 필터)
- GET /v1/metrics      : 메트릭 시리즈 목록 (service 필터)
- GET /v1/traces       : 트레이스 목록 (service, status, limit 필터)
- GET /v1/traces/{id}  : 트레이스 단건 상세

환경 변수:
  OPENSEARCH_URL   : 설정 시 실제 OpenSearch에서 데이터 조회 (미설정 시 mock 사용)
  AMP_ENDPOINT     : Amazon Managed Prometheus 엔드포인트 (메트릭)
  ALLOWED_ORIGINS  : CORS 허용 오리진 (기본: http://localhost:3000)
"""

import os
import time
import random
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ============================================================
# App 설정
# ============================================================

OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL")  # 미설정 시 mock 사용
AMP_ENDPOINT = os.environ.get("AMP_ENDPOINT")
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app = FastAPI(title="observability-service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Mock 데이터 (dashboard/src/lib/mock.ts 의 types.ts 기준 포맷)
# OpenSearch/AMP 연결 전까지 이 데이터로 동작
# ============================================================

_MOCK_LOGS = [
    {
        "id": "log-1",
        "timestamp": "2026-03-12T10:30:21Z",
        "service": "checkout",
        "env": "prod",
        "level": "ERROR",
        "message": "Payment provider timeout after 3 retries",
        "metadata": {
            "userId": "user-12345",
            "requestId": "req-abc123",
            "traceId": "trace-001-001",
            "spanId": "span-001-002",
            "retryCount": 3,
            "timeout_ms": 5000,
        },
        "tags": {"endpoint": "/api/checkout/pay", "method": "POST"},
    },
    {
        "id": "log-2",
        "timestamp": "2026-03-12T10:30:18Z",
        "service": "gateway",
        "env": "prod",
        "level": "WARN",
        "message": "Upstream latency above threshold p95=1.4s",
        "metadata": {
            "requestId": "req-def456",
            "traceId": "trace-002-001",
            "latency_p95_ms": 1400,
            "threshold_ms": 1000,
        },
        "tags": {},
    },
    {
        "id": "log-3",
        "timestamp": "2026-03-12T10:30:10Z",
        "service": "search",
        "env": "staging",
        "level": "INFO",
        "message": "Index refresh completed in 320ms",
        "metadata": {
            "indexName": "products-v3",
            "documents": 2345678,
            "duration_ms": 320,
        },
        "tags": {},
    },
    {
        "id": "log-4",
        "timestamp": "2026-03-12T10:30:02Z",
        "service": "payments",
        "env": "prod",
        "level": "ERROR",
        "message": "Circuit breaker opened for external gateway",
        "metadata": {
            "service": "stripe-gateway",
            "failureRate": 0.95,
            "threshold": 0.5,
            "traceId": "trace-003-001",
        },
        "tags": {},
    },
    {
        "id": "log-5",
        "timestamp": "2026-03-12T10:29:55Z",
        "service": "notifications",
        "env": "prod",
        "level": "WARN",
        "message": "Email queue depth: 45234 (threshold: 10000)",
        "metadata": {"queueDepth": 45234, "threshold": 10000},
        "tags": {},
    },
    {
        "id": "log-6",
        "timestamp": "2026-03-12T10:29:48Z",
        "service": "auth",
        "env": "prod",
        "level": "INFO",
        "message": "Token blacklist refresh: 156 tokens revoked",
        "metadata": {
            "tokensRevoked": 156,
            "duration_ms": 234,
            "blacklistSize": 5670,
        },
        "tags": {},
    },
]

_MOCK_METRICS = [
    {
        "id": "metric-error-rate",
        "name": "Error Rate",
        "unit": "%",
        "service": "checkout",
        "points": [
            {"ts": int(time.time() * 1000) - (60 - i) * 60000,
             "value": round(2.3 + (random.random() - 0.5) * 1.5, 3)}
            for i in range(60)
        ],
        "color": "#EF4444",
    },
    {
        "id": "metric-latency-p95",
        "name": "Latency P95",
        "unit": "ms",
        "service": "checkout",
        "points": [
            {"ts": int(time.time() * 1000) - (60 - i) * 60000,
             "value": round(450 + (random.random() - 0.5) * 200)}
            for i in range(60)
        ],
        "color": "#3B82F6",
    },
    {
        "id": "metric-throughput",
        "name": "Throughput",
        "unit": "req/s",
        "service": "checkout",
        "points": [
            {"ts": int(time.time() * 1000) - (60 - i) * 60000,
             "value": round(1200 + (random.random() - 0.5) * 300)}
            for i in range(60)
        ],
        "color": "#10B981",
    },
    {
        "id": "metric-cpu",
        "name": "CPU Usage",
        "unit": "%",
        "service": "checkout",
        "instance": "i-12345",
        "points": [
            {"ts": int(time.time() * 1000) - (60 - i) * 60000,
             "value": round(65 + (random.random() - 0.5) * 25, 2)}
            for i in range(60)
        ],
        "color": "#F59E0B",
    },
]

_MOCK_TRACES = [
    {
        "id": "trace-001-001",
        "service": "checkout",
        "operation": "POST /api/checkout",
        "startTime": int(time.time() * 1000) - 120000,
        "duration": 520,
        "status": "slow",
        "status_code": 200,
        "spans": [
            {
                "id": "span-1",
                "traceId": "trace-001-001",
                "service": "api-gateway",
                "operation": "web-request",
                "startTime": int(time.time() * 1000) - 120000,
                "duration": 520,
                "status": "ok",
            },
            {
                "id": "span-2",
                "traceId": "trace-001-001",
                "parentSpanId": "span-1",
                "service": "checkout",
                "operation": "validate-cart",
                "startTime": int(time.time() * 1000) - 119955,
                "duration": 45,
                "status": "ok",
            },
            {
                "id": "span-3",
                "traceId": "trace-001-001",
                "parentSpanId": "span-1",
                "service": "payments",
                "operation": "charge-payment",
                "startTime": int(time.time() * 1000) - 119800,
                "duration": 250,
                "status": "slow",
                "tags": {"external_service": "stripe"},
            },
        ],
        "tags": {"http.method": "POST"},
    },
    {
        "id": "trace-002-001",
        "service": "search",
        "operation": "GET /api/search",
        "startTime": int(time.time() * 1000) - 90000,
        "duration": 85,
        "status": "ok",
        "status_code": 200,
        "spans": [
            {
                "id": "span-search-1",
                "traceId": "trace-002-001",
                "service": "search",
                "operation": "query-index",
                "startTime": int(time.time() * 1000) - 90000,
                "duration": 85,
                "status": "ok",
            }
        ],
        "tags": {},
    },
]


# ============================================================
# 헬퍼: 실제 데이터 소스 선택
# ============================================================

def _get_logs_data() -> list:
    """OpenSearch 연결 시 실제 쿼리, 아니면 mock"""
    if OPENSEARCH_URL:
        # TODO: OpenSearch 쿼리 구현
        # from opensearchpy import OpenSearch
        # client = OpenSearch(OPENSEARCH_URL)
        # response = client.search(index="logs-*", body={"query": {"match_all": {}}})
        # return [hit["_source"] for hit in response["hits"]["hits"]]
        pass
    return list(_MOCK_LOGS)


def _get_metrics_data() -> list:
    """AMP 연결 시 실제 쿼리, 아니면 mock"""
    if AMP_ENDPOINT:
        # TODO: AWS SDK로 AMP 쿼리
        # import boto3
        # client = boto3.client("aps")
        # response = client.query_metrics(...)
        pass
    return list(_MOCK_METRICS)


def _get_traces_data() -> list:
    """OpenSearch 연결 시 실제 트레이스 쿼리, 아니면 mock"""
    if OPENSEARCH_URL:
        # TODO: OpenSearch traces 인덱스 쿼리
        pass
    return list(_MOCK_TRACES)


# ============================================================
# 엔드포인트
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "observability-service",
        "ts": datetime.now(timezone.utc).isoformat(),
        "data_source": "opensearch" if OPENSEARCH_URL else "mock",
    }


@app.get("/v1/logs")
def get_logs(
    service: Optional[str] = None,
    level: Optional[str] = None,
    env: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
):
    logs = _get_logs_data()

    if service:
        logs = [l for l in logs if l["service"] == service]
    if level:
        logs = [l for l in logs if l["level"] == level.upper()]
    if env:
        logs = [l for l in logs if l.get("env") == env]

    total = len(logs)
    return {"logs": logs[offset : offset + limit], "total": total}


@app.get("/v1/metrics")
def get_metrics(service: Optional[str] = None):
    metrics = _get_metrics_data()

    if service:
        metrics = [m for m in metrics if m.get("service") == service]

    return metrics


@app.get("/v1/traces")
def get_traces(
    service: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
):
    traces = _get_traces_data()

    if service:
        traces = [t for t in traces if t["service"] == service]
    if status:
        traces = [t for t in traces if t["status"] == status]

    total = len(traces)
    return {"traces": traces[offset : offset + limit], "total": total}


@app.get("/v1/traces/{trace_id}")
def get_trace_detail(trace_id: str):
    traces = _get_traces_data()
    for trace in traces:
        if trace["id"] == trace_id:
            return trace
    raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
