from fastapi import APIRouter
from .stream import router as stream_router
from .backlog import router as backlog_router
from .infra import router as infra_router
from .container import router as container_router
from .host import router as host_router
from .jvm import router as jvm_router
from .latency import router as latency_router
from .service_health import router as service_health_router

router = APIRouter()

router.include_router(stream_router)
router.include_router(backlog_router)
router.include_router(infra_router)
router.include_router(container_router)
router.include_router(host_router)
router.include_router(jvm_router)
router.include_router(latency_router)
router.include_router(service_health_router)
