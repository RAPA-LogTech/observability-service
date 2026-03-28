from fastapi import APIRouter
import asyncio
from ..services.observability_service import list_service_health

router = APIRouter()

@router.get("/v1/metrics/service-health")
async def get_service_health() -> list:
    return await asyncio.get_event_loop().run_in_executor(None, list_service_health)
