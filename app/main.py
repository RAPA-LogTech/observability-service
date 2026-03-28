import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api.health import router as health_router
from .logs.index import router as logs_router
from .traces.index import router as traces_router
from .metrics.index import router as metrics_router
from .api.metrics_jvm import router as metrics_jvm_router
from .api.metrics_latency import router as metrics_latency_router
from .api.metrics_infra import router as metrics_infra_router
from .api.metrics_service_health import router as metrics_service_health_router
from .api.overview import router as overview_router
from .api.traces import router as traces_router
from .core.config import get_settings

logger = logging.getLogger("uvicorn.error")


def create_app() -> FastAPI:
    settings = get_settings()

    fastapi_app = FastAPI(title=settings.service_name, version="0.1.0")

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @fastapi_app.middleware("http")
    async def log_request_url(request: Request, call_next):
        logger.info("Incoming request: %s %s", request.method, request.url)
        return await call_next(request)


    fastapi_app.include_router(health_router)
    fastapi_app.include_router(logs_router)
    fastapi_app.include_router(metrics_router)
    fastapi_app.include_router(traces_router)
    fastapi_app.include_router(overview_router)

    return fastapi_app


app = create_app()
