from fastapi import APIRouter

from ..services.observability_service import list_metrics

router = APIRouter(prefix="/v1", tags=["metrics"])


@router.get("/metrics")
def get_metrics(service: str | None = None) -> list[dict]:
    return list_metrics(service=service)
