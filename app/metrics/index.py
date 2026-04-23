from fastapi import APIRouter

from .backlog import router as backlog_router
from .container import router as container_router
from .databases import router as databases_router
from .host import router as host_router
from .infra import router as infra_router
from .jvm import router as jvm_router
from .latency import router as latency_router
from .query import router as query_router
from .rds import router as rds_router
from .service_health import router as service_health_router
from .stream import router as stream_router

router = APIRouter(prefix="/v1/metrics")

router.include_router(query_router)
router.include_router(stream_router)
router.include_router(backlog_router)
router.include_router(infra_router)
router.include_router(container_router)
router.include_router(host_router)
router.include_router(jvm_router)
router.include_router(databases_router)
router.include_router(rds_router)
router.include_router(latency_router)
router.include_router(service_health_router)
