import asyncio
import json
import time
from collections import deque
from typing import Any, Literal

from .observability_service import list_logs, list_metrics, list_traces

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

        self._seen_ids: set[str] = set()
        self._last_metric_points: dict[str, tuple[int, float]] = {}

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
        """서비스 시작 시 OpenSearch의 기존 데이터를 history에 미리 적재.
        이후 _run 루프는 _seen_ids에 없는 신규 항목만 스트리밍한다."""
        if self.kind == "logs":
            result = list_logs(limit=self.max_history, offset=0)
            items = result.get("logs", []) if isinstance(result, dict) else []
            # OpenSearch는 최신순 반환 → 가장 오래된 것부터 history에 넣어 cursor 단조증가 유지
            for item in reversed(items):
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "")
                if not item_id or item_id in self._seen_ids:
                    continue
                self._seen_ids.add(item_id)
                self.cursor += 1
                self.history.append({"ts": _now_ms(), "log": item, "cursor": self.cursor})

        elif self.kind == "traces":
            result = list_traces(limit=self.max_history, offset=0)
            items = result.get("traces", []) if isinstance(result, dict) else []
            for item in reversed(items):
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "")
                if not item_id or item_id in self._seen_ids:
                    continue
                self._seen_ids.add(item_id)
                self.cursor += 1
                self.history.append({"ts": _now_ms(), "trace": item, "cursor": self.cursor})

        self.sequence = self.cursor

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.min_delay_seconds)
            payload = self._next_payload()
            if payload is None:
                continue

            self.cursor += 1
            payload["cursor"] = self.cursor

            self.history.append(payload)
            stale: list[asyncio.Queue[dict[str, Any]]] = []
            for queue in self.subscribers:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

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

    def _next_payload(self) -> dict[str, Any] | None:
        self.sequence += 1

        if self.kind == "logs":
            return self._next_log_payload()
        if self.kind == "metrics":
            return self._next_metric_payload()
        return self._next_trace_payload()

    def _next_log_payload(self) -> dict[str, Any] | None:
        result = list_logs(limit=1000, offset=0)
        logs = result.get("logs", []) if isinstance(result, dict) else []
        if not isinstance(logs, list):
            return None

        for item in logs:
            if not isinstance(item, dict):
                continue
            log_id = str(item.get("id") or "")
            if not log_id or log_id in self._seen_ids:
                continue

            self._seen_ids.add(log_id)
            if len(self._seen_ids) > 4000:
                self._seen_ids = set(list(self._seen_ids)[-2500:])
            return {"ts": _now_ms(), "log": item}

        return None

    def _next_metric_payload(self) -> dict[str, Any] | None:
        metrics = list_metrics()
        if not isinstance(metrics, list):
            return None

        now_ms = _now_ms()
        points: list[dict[str, Any]] = []

        for series in metrics:
            if not isinstance(series, dict):
                continue
            series_id = str(series.get("id") or "")
            series_points = series.get("points", [])
            if not series_id or not isinstance(series_points, list) or not series_points:
                continue

            last_point = series_points[-1]
            if not isinstance(last_point, dict):
                continue

            ts = int(last_point.get("ts") or now_ms)
            value = float(last_point.get("value") or 0)
            prev = self._last_metric_points.get(series_id)
            if prev and prev[0] == ts and prev[1] == value:
                continue

            self._last_metric_points[series_id] = (ts, value)
            points.append({"id": series_id, "ts": ts, "value": value})

        if not points:
            return None
        return {"ts": now_ms, "points": points}

    def _next_trace_payload(self) -> dict[str, Any] | None:
        result = list_traces(limit=200, offset=0)
        traces = result.get("traces", []) if isinstance(result, dict) else []
        if not isinstance(traces, list):
            return None

        for item in traces:
            if not isinstance(item, dict):
                continue
            trace_id = str(item.get("id") or "")
            if not trace_id or trace_id in self._seen_ids:
                continue

            self._seen_ids.add(trace_id)
            if len(self._seen_ids) > 4000:
                self._seen_ids = set(list(self._seen_ids)[-2500:])
            return {"ts": _now_ms(), "trace": item}

        return None


_LOG_STATE = _StreamState("logs", max_history=5000, min_delay_seconds=2.2, max_delay_seconds=6.8)
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
