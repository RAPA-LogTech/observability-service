from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.health import router as health_router
from .api.logs import router as logs_router
from .api.metrics import router as metrics_router
from .api.traces import router as traces_router
from .core.config import get_settings


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

    fastapi_app.include_router(health_router)
    fastapi_app.include_router(logs_router)
    fastapi_app.include_router(metrics_router)
    fastapi_app.include_router(traces_router)

    return fastapi_app


app = create_app()
