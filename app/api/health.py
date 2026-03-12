from datetime import datetime, timezone

from fastapi import APIRouter

from ..core.config import get_settings
from ..services.observability_service import get_data_source_name

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.service_name,
        "environment": settings.environment,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data_source": get_data_source_name(),
    }
