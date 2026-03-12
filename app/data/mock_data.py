import random
import time


def _now_ms() -> int:
    return int(time.time() * 1000)


def build_mock_logs() -> list[dict]:
    return [
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


def build_mock_metrics() -> list[dict]:
    now = _now_ms()

    def points(base_value: float, variance: float, digits: int = 2) -> list[dict]:
        return [
            {
                "ts": now - (60 - i) * 60000,
                "value": round(base_value + (random.random() - 0.5) * variance, digits),
            }
            for i in range(60)
        ]

    return [
        {
            "id": "metric-error-rate",
            "name": "Error Rate",
            "unit": "%",
            "service": "checkout",
            "points": points(2.3, 1.5, 3),
            "color": "#EF4444",
        },
        {
            "id": "metric-latency-p95",
            "name": "Latency P95",
            "unit": "ms",
            "service": "checkout",
            "points": points(450, 200, 0),
            "color": "#3B82F6",
        },
        {
            "id": "metric-throughput",
            "name": "Throughput",
            "unit": "req/s",
            "service": "checkout",
            "points": points(1200, 300, 0),
            "color": "#10B981",
        },
        {
            "id": "metric-cpu",
            "name": "CPU Usage",
            "unit": "%",
            "service": "checkout",
            "instance": "i-12345",
            "points": points(65, 25, 2),
            "color": "#F59E0B",
        },
    ]


def build_mock_traces() -> list[dict]:
    now = _now_ms()
    return [
        {
            "id": "trace-001-001",
            "service": "checkout",
            "operation": "POST /api/checkout",
            "startTime": now - 120000,
            "duration": 520,
            "status": "slow",
            "status_code": 200,
            "spans": [
                {
                    "id": "span-1",
                    "traceId": "trace-001-001",
                    "service": "api-gateway",
                    "operation": "web-request",
                    "startTime": now - 120000,
                    "duration": 520,
                    "status": "ok",
                },
                {
                    "id": "span-2",
                    "traceId": "trace-001-001",
                    "parentSpanId": "span-1",
                    "service": "checkout",
                    "operation": "validate-cart",
                    "startTime": now - 119955,
                    "duration": 45,
                    "status": "ok",
                },
                {
                    "id": "span-3",
                    "traceId": "trace-001-001",
                    "parentSpanId": "span-1",
                    "service": "payments",
                    "operation": "charge-payment",
                    "startTime": now - 119800,
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
            "startTime": now - 90000,
            "duration": 85,
            "status": "ok",
            "status_code": 200,
            "spans": [
                {
                    "id": "span-search-1",
                    "traceId": "trace-002-001",
                    "service": "search",
                    "operation": "query-index",
                    "startTime": now - 90000,
                    "duration": 85,
                    "status": "ok",
                }
            ],
            "tags": {},
        },
    ]
