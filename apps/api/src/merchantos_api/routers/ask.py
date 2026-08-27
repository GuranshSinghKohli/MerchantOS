from uuid import UUID

from fastapi import APIRouter, Request
from merchantos_app import AskService
from pydantic import BaseModel, ConfigDict, Field

from merchantos_api.deps import db_engine, queue
from merchantos_api.publisher import publish_unpublished
from merchantos_api.session_auth import tenant_from_request

router = APIRouter(prefix="/api/v1", tags=["ask"])


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)


def _service() -> AskService:
    return AskService(db_engine())


@router.post("/ask", status_code=202)
def enqueue_ask(request: Request, body: AskBody) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    payload = _service().enqueue(ctx, body.question)
    publish_unpublished(db_engine(), queue())
    return payload


@router.get("/ask/{run_id}")
def get_ask(request: Request, run_id: UUID) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().get(ctx, run_id, run_kind="ask")


@router.get("/ask")
def list_asks(request: Request) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return {"runs": _service().list_runs(ctx, run_kind="ask")}


@router.post("/ask/{run_id}/cancel")
def cancel_ask(request: Request, run_id: UUID) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().cancel(ctx, run_id)
