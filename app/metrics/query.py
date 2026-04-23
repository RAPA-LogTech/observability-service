from fastapi import APIRouter, HTTPException

from ..services.observability_service import list_metrics

router = APIRouter()


@router.get("/")
def get_metrics(
    service: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> dict:
    result = list_metrics(service=service, start=start, end=end)
    if "__error__" in result:
        raise HTTPException(
            status_code=int(result.get("__status__", 502)),
            detail=str(result.get("__error__")),
        )
    return {"metrics": result}
