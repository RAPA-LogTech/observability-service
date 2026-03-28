from fastapi import APIRouter, HTTPException
import asyncio
from ..services.observability_service import list_latency_metrics

router = APIRouter()

@router.get("/v1/metrics/latency")
async def get_latency_metrics(
    service: str | None = None,
    start: int | None = None,
    end: int | None = None,
    limit: int | None = None,
) -> object:
    result = await asyncio.get_event_loop().run_in_executor(None, lambda: list_latency_metrics(service=service, start=start, end=end))
    if isinstance(result, dict) and "__error__" in result:
        raise HTTPException(
            status_code=int(result.get("__status__", 502)),
            detail=str(result.get("__error__")),
        )
    if limit is not None and isinstance(result, list):
        return result[:limit]
    return result
