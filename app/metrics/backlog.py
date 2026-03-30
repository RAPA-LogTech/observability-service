from fastapi import APIRouter, Query
from ..services.streaming_service import ensure_stream_started, get_stream_backlog

router = APIRouter()

@router.get("/backlog")
async def get_metrics_backlog(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    await ensure_stream_started("metrics")
    return get_stream_backlog("metrics", cursor, limit)
