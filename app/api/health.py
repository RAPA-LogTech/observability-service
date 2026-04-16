from datetime import datetime, timezone

from fastapi import APIRouter

from ..core.config import get_settings
from ..services.observability_service import get_data_source_name, get_dependency_health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Lightweight health check for k8s probes (no external dependencies)"""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.service_name,
        "environment": settings.environment,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
def health_ready() -> dict:
    """Readiness check with dependency validation (OpenSearch, AMP)"""
    settings = get_settings()
    dependency_health = get_dependency_health()
    overall_status = "ok" if dependency_health.get("all_ok") else "degraded"

    return {
        "status": overall_status,
        "service": settings.service_name,
        "environment": settings.environment,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data_source": get_data_source_name(),
        "dependencies": dependency_health,
    }
