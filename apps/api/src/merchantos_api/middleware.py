from collections.abc import Awaitable, Callable
from time import perf_counter

from merchantos_observability import bind_request_id, emit_metric, new_request_id
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id")
        request_id = incoming if incoming else new_request_id()
        request.state.request_id = request_id
        bind_request_id(request_id)
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        status = response.status_code
        emit_metric(
            "api_request",
            1,
            dimensions={
                "route": request.url.path,
                "method": request.method,
                "status_class": f"{status // 100}xx",
            },
        )
        emit_metric(
            "api_latency_ms",
            (perf_counter() - started) * 1000,
            unit="Milliseconds",
            dimensions={"route": request.url.path},
        )
        if status >= 500:
            emit_metric("api_5xx", 1, dimensions={"route": request.url.path})
        elif status >= 400:
            emit_metric("api_4xx", 1, dimensions={"route": request.url.path})
        return response
