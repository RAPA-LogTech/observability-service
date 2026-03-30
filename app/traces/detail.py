from fastapi import APIRouter, HTTPException
from ..services.observability_service import get_trace_detail

router = APIRouter()

@router.get("/{trace_id}")
def get_trace(trace_id: str) -> dict:
    trace = get_trace_detail(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return trace
