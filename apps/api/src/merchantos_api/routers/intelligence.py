from uuid import UUID

from fastapi import APIRouter, Request
from merchantos_app import AskService
from merchantos_domain import RunKind
from pydantic import BaseModel, ConfigDict, Field

from merchantos_api.deps import db_engine, queue
from merchantos_api.publisher import publish_unpublished
from merchantos_api.session_auth import tenant_from_request

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


class IntelligenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)


def _service() -> AskService:
    return AskService(db_engine())


@router.post("/query", status_code=202)
def enqueue_intelligence(request: Request, body: IntelligenceBody) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    payload = _service().enqueue(ctx, body.question, run_kind=RunKind.INTELLIGENCE.value)
    publish_unpublished(db_engine(), queue())
    return payload


@router.get("/{run_id}")
def get_intelligence(request: Request, run_id: UUID) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().get(ctx, run_id, run_kind="intelligence")


@router.get("")
def list_intelligence(request: Request) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return {"runs": _service().list_runs(ctx, run_kind="intelligence")}
