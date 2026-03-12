import asyncio
import json
import random
import time
from collections import deque
from contextlib import suppress
from copy import deepcopy
from typing import Any, Literal

from ..data.mock_data import build_mock_logs, build_mock_metrics, build_mock_traces

StreamKind = Literal["logs", "metrics", "traces"]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class _StreamState:
    def __init__(
        self,
        kind: StreamKind,
        max_history: int,
        min_delay_seconds: float,
        max_delay_seconds: float,
    ) -> None:
        self.kind = kind
        self.max_history = max_history
        self.min_delay_seconds = min_delay_seconds
        self.max_delay_seconds = max_delay_seconds

        self.history: deque[dict[str, Any]] = deque(maxlen=max_history)
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

        self.cursor = 0
        self.sequence = 0
        self.started = False
        self._task: asyncio.Task[None] | None = None
        self._start_lock = asyncio.Lock()

        self._log_templates: list[dict[str, Any]] = []
        self._trace_templates: list[dict[str, Any]] = []
        self._metric_state: list[dict[str, Any]] = []

    async def ensure_started(self) -> None:
        if self.started:
            return

        async with self._start_lock:
            if self.started:
                return
            self._bootstrap_state()
            self._task = asyncio.create_task(self._run(), name=f"{self.kind}-stream-producer")
            self.started = True

    def _bootstrap_state(self) -> None:
        if self.kind == "logs":
            self._log_templates = build_mock_logs()
            return

        if self.kind == "traces":
            self._trace_templates = build_mock_traces()
            return

        metrics = build_mock_metrics()
        self._metric_state = [
            {
                "id": item["id"],
                "unit": item.get("unit", ""),
                "value": item.get("points", [{}])[-1].get("value", 0),
            }
            for item in metrics
        ]

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(random.uniform(self.min_delay_seconds, self.max_delay_seconds))
            payload = self._next_payload()

            self.cursor += 1
            payload["cursor"] = self.cursor

            self.history.append(payload)
            stale: list[asyncio.Queue[dict[str, Any]]] = []
            for queue in self.subscribers:
                if queue.full():
                    with suppress(asyncio.QueueEmpty):
                        queue.get_nowait()

                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    stale.append(queue)

            for queue in stale:
                self.subscribers.discard(queue)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers.discard(queue)

    def backlog(self, after_cursor: int, limit: int) -> dict[str, Any]:
        safe_cursor = max(0, int(after_cursor))
        safe_limit = min(500, max(1, int(limit)))

        events = [item for item in self.history if item.get("cursor", 0) > safe_cursor][:safe_limit]
        next_cursor = events[-1]["cursor"] if events else safe_cursor
        latest_cursor = self.history[-1]["cursor"] if self.history else safe_cursor

        return {
            "events": events,
            "nextCursor": next_cursor,
            "hasMore": latest_cursor > next_cursor,
            "latestCursor": latest_cursor,
        }

    def latest_cursor(self) -> int:
        if not self.history:
            return 0
        return int(self.history[-1]["cursor"])

    def _next_payload(self) -> dict[str, Any]:
        self.sequence += 1

        if self.kind == "logs":
            return self._next_log_payload()
        if self.kind == "metrics":
            return self._next_metric_payload()
        return self._next_trace_payload()

    def _next_log_payload(self) -> dict[str, Any]:
        if not self._log_templates:
            self._log_templates = build_mock_logs()

        template = deepcopy(random.choice(self._log_templates))
        now_ms = _now_ms()
        level = random.choices(["INFO", "WARN", "ERROR", "DEBUG"], weights=[55, 25, 12, 8], k=1)[0]

        metadata = template.get("metadata") or {}
        metadata["requestId"] = f"req-{self.sequence:08d}"
        metadata["traceId"] = f"trace-live-{self.sequence:06d}"
        metadata["spanId"] = f"span-live-{self.sequence:06d}"

        template["id"] = f"log-live-{now_ms}-{self.sequence}"
        template["timestamp"] = _iso_now()
        template["level"] = level
        template["metadata"] = metadata

        return {"ts": now_ms, "log": template}

    def _next_metric_payload(self) -> dict[str, Any]:
        now_ms = _now_ms()
        points: list[dict[str, Any]] = []

        for item in self._metric_state:
            unit = str(item.get("unit", ""))
            value = float(item.get("value", 0))

            if unit == "%":
                delta = (random.random() - 0.5) * 1.2
                next_value = max(0, min(100, value + delta))
                rounded = round(next_value, 3)
            elif unit == "ms":
                delta = (random.random() - 0.5) * 24
                rounded = round(max(1, value + delta), 0)
            else:
                delta = (random.random() - 0.5) * 40
                rounded = round(max(0, value + delta), 2)

            item["value"] = rounded
            points.append({"id": item["id"], "ts": now_ms, "value": rounded})

        return {"ts": now_ms, "points": points}

    def _next_trace_payload(self) -> dict[str, Any]:
        if not self._trace_templates:
            self._trace_templates = build_mock_traces()

        template = deepcopy(random.choice(self._trace_templates))
        now_ms = _now_ms()
        status = random.choices(["ok", "slow", "error"], weights=[66, 22, 12], k=1)[0]

        base_duration = int(template.get("duration", 100))
        multiplier = 1.0
        if status == "slow":
            multiplier = 1.35
        if status == "error":
            multiplier = 1.6
        duration = max(20, int(base_duration * multiplier * random.uniform(0.85, 1.15)))

        trace_id = f"trace-live-{now_ms}-{self.sequence}"
        start_time = now_ms - duration - random.randint(0, 900)

        spans = template.get("spans", [])
        id_map: dict[str, str] = {}
        for index, span in enumerate(spans, start=1):
            old_id = str(span.get("id", f"span-{index}"))
            id_map[old_id] = f"{trace_id}-span-{index}"

        for span in spans:
            old_parent = span.get("parentSpanId")
            old_id = str(span.get("id"))
            span["id"] = id_map.get(old_id, f"{trace_id}-span-x")
            span["traceId"] = trace_id
            if old_parent:
                span["parentSpanId"] = id_map.get(str(old_parent))

            span_duration = int(span.get("duration", 10))
            span_multiplier = 1.0 if status == "ok" else 1.22 if status == "slow" else 1.4
            span["duration"] = max(
                2,
                int(span_duration * span_multiplier * random.uniform(0.8, 1.2)),
            )
            span["startTime"] = start_time + random.randint(0, max(1, duration - 1))

        template["id"] = trace_id
        template["startTime"] = start_time
        template["duration"] = duration
        template["status"] = status
        template["status_code"] = 200 if status == "ok" else 429 if status == "slow" else 500

        return {"ts": now_ms, "trace": template}


_LOG_STATE = _StreamState("logs", max_history=1000, min_delay_seconds=2.2, max_delay_seconds=6.8)
_METRIC_STATE = _StreamState(
    "metrics",
    max_history=400,
    min_delay_seconds=4.5,
    max_delay_seconds=9.5,
)
_TRACE_STATE = _StreamState(
    "traces",
    max_history=300,
    min_delay_seconds=3.5,
    max_delay_seconds=11.0,
)


def _state(kind: StreamKind) -> _StreamState:
    if kind == "logs":
        return _LOG_STATE
    if kind == "metrics":
        return _METRIC_STATE
    return _TRACE_STATE


async def ensure_stream_started(kind: StreamKind) -> None:
    await _state(kind).ensure_started()


def subscribe_stream(kind: StreamKind) -> asyncio.Queue[dict[str, Any]]:
    return _state(kind).subscribe()


def unsubscribe_stream(kind: StreamKind, queue: asyncio.Queue[dict[str, Any]]) -> None:
    _state(kind).unsubscribe(queue)


def get_stream_backlog(kind: StreamKind, after_cursor: int, limit: int) -> dict[str, Any]:
    return _state(kind).backlog(after_cursor, limit)


def get_latest_stream_cursor(kind: StreamKind) -> int:
    return _state(kind).latest_cursor()


def encode_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
