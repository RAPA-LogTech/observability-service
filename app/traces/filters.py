from fastapi import APIRouter
from ..services.observability_service import list_trace_filters

router = APIRouter()


@router.get("/filters")
def get_trace_filters() -> dict:
    return list_trace_filters()