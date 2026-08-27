from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from merchantos_domain import DomainError
from merchantos_observability import get_logger

logger = get_logger(__name__)


def problem(
    *,
    status: int,
    title: str,
    detail: str,
    request_id: str,
    type_suffix: str,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://merchantos.dev/errors/{type_suffix}",
        "title": title,
        "status": status,
        "detail": detail,
        "request_id": request_id,
    }
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning("domain_error", error=str(exc), request_id=request_id)
        status = getattr(exc, "http_status", 400)
        title = "Bad Request"
        if status == 401:
            title = "Unauthorized"
        elif status == 403:
            title = "Forbidden"
        elif status == 404:
            title = "Not Found"
        elif status == 409:
            title = "Conflict"
        elif status == 422:
            title = "Unprocessable Entity"
        elif status == 503:
            title = "Service Unavailable"
        return problem(
            status=status,
            title=title,
            detail=str(exc),
            request_id=request_id,
            type_suffix="domain",
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error("unhandled_error", error_type=type(exc).__name__, request_id=request_id)
        return problem(
            status=500,
            title="Internal Server Error",
            detail="An unexpected error occurred.",
            request_id=request_id,
            type_suffix="internal",
        )
