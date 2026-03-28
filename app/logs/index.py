from fastapi import APIRouter
from .query import router as query_router
from .stream import router as stream_router
from .backlog import router as backlog_router

router = APIRouter()

router.include_router(query_router)
router.include_router(stream_router)
router.include_router(backlog_router)
