from fastapi import APIRouter, Query

from ..services.observability_service import list_logs

router = APIRouter(prefix="/v1", tags=["logs"])


@router.get("/logs")
def get_logs(
    service: str | None = None,
    level: str | None = None,
    env: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
) -> dict:
    return list_logs(service=service, level=level, env=env, limit=limit, offset=offset)
