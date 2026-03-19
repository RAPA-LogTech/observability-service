#!/usr/bin/env python3
"""
로컬 개발용 OpenSearch 샘플 데이터 로드 스크립트
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

OPENSEARCH_URL = "http://localhost:9200"
SAMPLE_DATA_DIR = Path(__file__).parent.parent.parent / "dashboard" / "public" / "data"


def create_index(index_name):
    """인덱스 생성"""
    url = f"{OPENSEARCH_URL}/{index_name}"
    
    # 이미 있으면 스킵
    resp = requests.get(url)
    if resp.status_code == 200:
        print(f"✓ Index '{index_name}' already exists")
        return
    
    if index_name == "logs-*":
        mappings = {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "service": {
                        "properties": {
                            "name": {"type": "keyword"}
                        }
                    },
                    "level": {"type": "keyword"},
                    "message": {"type": "text"},
                    "host": {"type": "keyword"},
                    "trace_id": {"type": "keyword"},
                    "span_id": {"type": "keyword"},
                    "request_id": {"type": "keyword"},
                }
            }
        }
    elif index_name == "metrics-*":
        mappings = {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "metric_name": {"type": "keyword"},
                    "value": {"type": "double"},
                    "service": {"type": "keyword"},
                    "host": {"type": "keyword"},
                    "tags": {"type": "nested"}
                }
            }
        }
    elif index_name == "traces-*":
        mappings = {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "trace_id": {"type": "keyword"},
                    "span_id": {"type": "keyword"},
                    "parent_span_id": {"type": "keyword"},
                    "service": {
                        "properties": {
                            "name": {"type": "keyword"}
                        }
                    },
                    "span_name": {"type": "keyword"},
                    "duration": {"type": "double"},
                    "status": {"type": "keyword"},
                }
            }
        }
    else:
        mappings = {}
    
    resp = requests.put(url, json=mappings)
    if resp.status_code in [200, 201]:
        print(f"✓ Created index '{index_name}'")
    else:
        print(f"✗ Failed to create index '{index_name}': {resp.text}")


def load_logs():
    """샘플 로그 데이터 로드"""
    log_file = SAMPLE_DATA_DIR / "logs-example.json"
    if not log_file.exists():
        print(f"✗ Log file not found: {log_file}")
        return
    
    with open(log_file) as f:
        logs = json.load(f)
    
    index_name = f"logs-{datetime.now().strftime('%Y.%m.%d')}"
    create_index(index_name)
    
    count = 0
    for log in logs if isinstance(logs, list) else logs.get("logs", []):
        # 타임스탐프 추가
        if "timestamp" not in log:
            log["timestamp"] = datetime.now().isoformat()
        
        doc_id = log.get("trace_id", log.get("request_id", count))
        resp = requests.post(
            f"{OPENSEARCH_URL}/{index_name}/_doc/{doc_id}",
            json=log
        )
        if resp.status_code in [200, 201]:
            count += 1
        else:
            print(f"✗ Failed to index log: {resp.text}")
    
    print(f"✓ Loaded {count} log documents into '{index_name}'")


def load_metrics():
    """샘플 메트릭 데이터 로드"""
    metric_file = SAMPLE_DATA_DIR / "metrics-example.json"
    if not metric_file.exists():
        print(f"✗ Metric file not found: {metric_file}")
        return
    
    with open(metric_file) as f:
        metrics = json.load(f)
    
    index_name = f"metrics-{datetime.now().strftime('%Y.%m.%d')}"
    create_index(index_name)
    
    count = 0
    for metric in metrics if isinstance(metrics, list) else metrics.get("metrics", []):
        if "timestamp" not in metric:
            metric["timestamp"] = datetime.now().isoformat()
        
        resp = requests.post(
            f"{OPENSEARCH_URL}/{index_name}/_doc",
            json=metric
        )
        if resp.status_code in [200, 201]:
            count += 1
        else:
            print(f"✗ Failed to index metric: {resp.text}")
    
    print(f"✓ Loaded {count} metric documents into '{index_name}'")


def load_traces():
    """샘플 트레이스 데이터 로드"""
    trace_file = SAMPLE_DATA_DIR / "traces-example.json"
    if not trace_file.exists():
        print(f"✗ Trace file not found: {trace_file}")
        return
    
    with open(trace_file) as f:
        traces = json.load(f)
    
    index_name = f"traces-{datetime.now().strftime('%Y.%m.%d')}"
    create_index(index_name)
    
    count = 0
    for trace in traces if isinstance(traces, list) else traces.get("traces", []):
        if "timestamp" not in trace:
            trace["timestamp"] = datetime.now().isoformat()
        
        doc_id = trace.get("trace_id", count)
        resp = requests.post(
            f"{OPENSEARCH_URL}/{index_name}/_doc/{doc_id}",
            json=trace
        )
        if resp.status_code in [200, 201]:
            count += 1
        else:
            print(f"✗ Failed to index trace: {resp.text}")
    
    print(f"✓ Loaded {count} trace documents into '{index_name}'")


def main():
    """메인 함수"""
    print("=" * 60)
    print("로컬 OpenSearch 샘플 데이터 로드")
    print("=" * 60)
    
    # OpenSearch 연결 확인
    max_retries = 10
    for i in range(max_retries):
        try:
            resp = requests.get(f"{OPENSEARCH_URL}/_cluster/health", timeout=2)
            if resp.status_code == 200:
                print(f"✓ OpenSearch is ready at {OPENSEARCH_URL}")
                break
        except requests.ConnectionError:
            if i < max_retries - 1:
                print(f"⏳ Waiting for OpenSearch... ({i+1}/{max_retries})")
                time.sleep(2)
            else:
                print(f"✗ Failed to connect to OpenSearch at {OPENSEARCH_URL}")
                sys.exit(1)
    
    print("\n로드 시작...")
    load_logs()
    load_metrics()
    load_traces()
    
    print("\n" + "=" * 60)
    print("✓ 샘플 데이터 로드 완료")
    print("=" * 60)
    print(f"\nOpenSearch 대시보드: {OPENSEARCH_URL}/_dashboards")
    print(f"observability-service: http://localhost:8081/docs")


if __name__ == "__main__":
    main()
