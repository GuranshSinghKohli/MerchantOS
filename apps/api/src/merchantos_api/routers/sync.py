from uuid import UUID

from fastapi import APIRouter, Request
from merchantos_domain import UnauthorizedError
from pydantic import BaseModel, ConfigDict, Field

from merchantos_api.deps import db_engine, queue
from merchantos_api.session_cookie import SESSION_COOKIE
from merchantos_api.sync_service import enqueue_store_sync, list_store_sync

router = APIRouter(prefix="/api/v1/store", tags=["sync"])


class SyncEnqueueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="initial")


def _session_id(request: Request) -> UUID:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise UnauthorizedError("not authenticated")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise UnauthorizedError("not authenticated") from exc


@router.post("/sync", status_code=202)
def enqueue_sync(request: Request, body: SyncEnqueueBody) -> dict[str, object]:
    request_id = UUID(str(request.state.request_id))
    jobs = enqueue_store_sync(
        engine=db_engine(),
        queue=queue(),
        session_id=_session_id(request),
        request_id=request_id,
        kind=body.kind,
    )
    return {"jobs": jobs}


@router.get("/sync")
def sync_status(request: Request) -> dict[str, object]:
    request_id = UUID(str(request.state.request_id))
    return list_store_sync(
        engine=db_engine(),
        session_id=_session_id(request),
        request_id=request_id,
    )
