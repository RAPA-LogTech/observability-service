from fastapi import APIRouter, Query
from ..services.streaming_service import ensure_stream_started, get_stream_backlog

router = APIRouter()

@router.get("/logs/backlog")
async def get_logs_backlog(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict:
    await ensure_stream_started("logs")
    return get_stream_backlog("logs", cursor, limit)
