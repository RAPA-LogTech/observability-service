import time
from datetime import datetime, timezone

import boto3
from fastapi import APIRouter, Query

from ..services.observability_service import get_settings

router = APIRouter()


@router.get("/rds")
def query_rds_metrics(
    start: int = Query(None, description="시작 타임스탬프(ms)", alias="start"),
    end: int = Query(None, description="끝 타임스탬프(ms)", alias="end"),
    step: int = Query(60, description="step(초)", alias="step"),
):
    settings = get_settings()
    now_ms = int(time.time() * 1000)
    end_ms = end or now_ms
    start_ms = start or (end_ms - 10 * 60 * 1000)

    if not settings.rds_instance_identifier:
        return []

    if step < 60:
        step = 60

    cw = boto3.client("cloudwatch", region_name=settings.aws_region)
    dimensions = [{"Name": "DBInstanceIdentifier", "Value": settings.rds_instance_identifier}]

    specs = [
        ("cpu", "rds_cpu_utilization", "CPUUtilization", "%"),
        ("conn", "rds_database_connections", "DatabaseConnections", ""),
        ("free", "rds_freeable_memory", "FreeableMemory", "bytes"),
        ("read", "rds_read_latency", "ReadLatency", "s"),
        ("write", "rds_write_latency", "WriteLatency", "s"),
    ]

    queries = [
        {
            "Id": query_id,
            "MetricStat": {
                "Metric": {
                    "Namespace": "AWS/RDS",
                    "MetricName": metric_name,
                    "Dimensions": dimensions,
                },
                "Period": step,
                "Stat": "Average",
            },
            "ReturnData": True,
        }
        for query_id, _, metric_name, _ in specs
    ]

    try:
        resp = cw.get_metric_data(
            MetricDataQueries=queries,
            StartTime=datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc),
            EndTime=datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc),
        )
    except Exception:
        return []

    results_by_id = {item.get("Id"): item for item in resp.get("MetricDataResults", [])}

    results = []
    for query_id, series_name, _, unit in specs:
        result = results_by_id.get(query_id, {})
        timestamps = result.get("Timestamps", [])
        values = result.get("Values", [])
        if not timestamps or not values:
            continue

        pairs = sorted(zip(timestamps, values), key=lambda pair: pair[0])
        points = []
        for ts, value in pairs:
            if ts is None or value is None:
                continue
            points.append({"ts": int(ts.timestamp() * 1000), "value": float(value)})

        if not points:
            continue

        results.append(
            {
                "id": f"{series_name}_rds",
                "name": series_name,
                "unit": unit,
                "service": "rds",
                "instance": settings.rds_instance_identifier,
                "points": points,
            }
        )

    return results
