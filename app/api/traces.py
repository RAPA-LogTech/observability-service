from fastapi import APIRouter, HTTPException, Query

from ..services.observability_service import get_trace_detail, list_traces

router = APIRouter(prefix="/v1", tags=["traces"])


@router.get("/traces")
def get_traces(
    service: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
) -> dict:
    return list_traces(service=service, status=status, limit=limit, offset=offset)


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    trace = get_trace_detail(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return trace
