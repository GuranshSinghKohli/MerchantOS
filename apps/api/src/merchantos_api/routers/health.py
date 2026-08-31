from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from merchantos_db import ping_database
from merchantos_observability import get_logger
from redis import Redis
from sqlalchemy import Engine

from merchantos_api import __version__
from merchantos_api.deps import db_engine, queue, redis_client, settings

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    checks: dict[str, bool] = {}

    try:
        engine: Engine = db_engine()
        ping_database(engine)
        checks["postgres"] = True
    except Exception:
        logger.warning("ready_postgres_failed")
        checks["postgres"] = False

    if settings().redis_url:
        try:
            client: Redis = redis_client()
            checks["redis"] = client.ping() is True
        except Exception:
            logger.warning("ready_redis_failed")
            checks["redis"] = False
    else:
        checks["redis"] = True

    payload: dict[str, Any] = {
        "status": "ok" if all(checks.values()) else "unavailable",
        "postgres": checks["postgres"],
        "redis": checks["redis"] if settings().redis_url else "skipped",
        "request_id": getattr(request.state, "request_id", None),
    }
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/ready/queue")
def ready_queue() -> dict[str, bool]:
    """Optional probe. Queue is not required for /ready in Phase 1."""
    try:
        queue().ping()
        return {"queue": True}
    except Exception:
        logger.warning("ready_queue_failed")
        return {"queue": False}
