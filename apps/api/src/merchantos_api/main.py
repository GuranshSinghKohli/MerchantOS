from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from merchantos_observability import configure_logging, get_logger

from merchantos_api import __version__
from merchantos_api.errors import register_exception_handlers
from merchantos_api.middleware import RequestIdMiddleware
from merchantos_api.routers.actions import router as actions_router
from merchantos_api.routers.analytics import router as analytics_router
from merchantos_api.routers.ask import router as ask_router
from merchantos_api.routers.auth import router as auth_router
from merchantos_api.routers.health import router as health_router
from merchantos_api.routers.intelligence import router as intelligence_router
from merchantos_api.routers.me import router as me_router
from merchantos_api.routers.sync import router as sync_router
from merchantos_api.routers.webhooks import router as webhook_router
from merchantos_api.settings import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level)
    get_logger(__name__).info("api_started", env=settings.app_env, version=__version__)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MerchantOS API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env == "dev" else None,
        redoc_url=None,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(sync_router)
    app.include_router(analytics_router)
    app.include_router(ask_router)
    app.include_router(intelligence_router)
    app.include_router(actions_router)
    app.include_router(webhook_router)
    return app


app = create_app()
