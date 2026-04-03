from fastapi import APIRouter
from .query import router as query_router
from .detail import router as detail_router
from .stream import router as stream_router
from .backlog import router as backlog_router
from .filters import router as filters_router

router = APIRouter(prefix="/v1/traces")

router.include_router(query_router)
router.include_router(detail_router)
router.include_router(stream_router)
router.include_router(backlog_router)
router.include_router(filters_router)
