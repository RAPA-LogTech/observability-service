from fastapi import APIRouter, HTTPException, Query

from ..services.observability_service import list_traces

router = APIRouter()


@router.get("/")
def get_traces(
    service: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict:
    result = list_traces(
        service=service,
        status=status,
        limit=limit,
        offset=offset,
        start_time=start_time,
        end_time=end_time,
    )
    if "__error__" in result:
        raise HTTPException(
            status_code=int(result.get("__status__", 502)),
            detail=str(result.get("__error__")),
        )
    return result
