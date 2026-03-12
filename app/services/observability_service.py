from ..core.config import get_settings
from ..data.mock_data import build_mock_logs, build_mock_metrics, build_mock_traces


def get_data_source_name() -> str:
    settings = get_settings()
    return "opensearch" if settings.opensearch_url else "mock"


def list_logs(
    service: str | None = None,
    level: str | None = None,
    env: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    settings = get_settings()

    # TODO: replace with actual OpenSearch query when opensearch_url exists.
    if settings.opensearch_url:
        logs = build_mock_logs()
    else:
        logs = build_mock_logs()

    if service:
        logs = [item for item in logs if item["service"] == service]
    if level:
        logs = [item for item in logs if item["level"] == level.upper()]
    if env:
        logs = [item for item in logs if item.get("env") == env]

    total = len(logs)
    return {"logs": logs[offset : offset + limit], "total": total}


def list_metrics(service: str | None = None) -> list[dict]:
    settings = get_settings()

    # TODO: replace with actual AMP query when amp_endpoint exists.
    if settings.amp_endpoint:
        metrics = build_mock_metrics()
    else:
        metrics = build_mock_metrics()

    if service:
        metrics = [item for item in metrics if item.get("service") == service]

    return metrics


def list_traces(
    service: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    settings = get_settings()

    # TODO: replace with actual trace index query when opensearch_url exists.
    if settings.opensearch_url:
        traces = build_mock_traces()
    else:
        traces = build_mock_traces()

    if service:
        traces = [item for item in traces if item["service"] == service]
    if status:
        traces = [item for item in traces if item["status"] == status]

    total = len(traces)
    return {"traces": traces[offset : offset + limit], "total": total}


def get_trace_detail(trace_id: str) -> dict | None:
    traces = build_mock_traces()
    for trace in traces:
        if trace["id"] == trace_id:
            return trace
    return None
