from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from merchantos_app.actions import ActionService, ApprovalService
from merchantos_domain import ActionType, DomainError, IntendedProductChange
from pydantic import BaseModel, ConfigDict, Field

from merchantos_api.deps import db_engine, queue
from merchantos_api.publisher import publish_unpublished
from merchantos_api.session_auth import tenant_from_request

router = APIRouter(prefix="/api/v1", tags=["actions"])


class ProposeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    resource_id: UUID
    rationale: str = Field(min_length=1, max_length=800)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = None
    status: Literal["ACTIVE", "DRAFT"] | None = None
    source_recommendation_id: str | None = Field(default=None, max_length=80)
    evidence: list[dict[str, str]] | None = None


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = True


def _actions() -> ActionService:
    return ActionService(db_engine())


def _approvals() -> ApprovalService:
    return ApprovalService(db_engine())


@router.post("/actions", status_code=201)
def propose_action(request: Request, body: ProposeBody) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    intended = IntendedProductChange(
        title=body.title,
        description=body.description,
        tags=tuple(body.tags) if body.tags is not None else None,
        status=body.status,
    )
    return _actions().propose(
        ctx,
        action_type=body.action_type,
        resource_id=body.resource_id,
        intended=intended,
        rationale=body.rationale,
        evidence_refs=body.evidence,
        source_recommendation_id=body.source_recommendation_id,
    )


@router.get("/actions")
def list_actions(request: Request) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return {"actions": _actions().list_actions(ctx)}


@router.get("/approvals")
def list_pending_approvals(request: Request) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return {
        "actions": _actions().list_actions(ctx, statuses=frozenset({"PROPOSED"})),
    }


@router.get("/actions/{action_id}")
def get_action(request: Request, action_id: UUID) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _actions().get(ctx, action_id)


@router.get("/approvals/{action_id}")
def get_approval_snapshot(request: Request, action_id: UUID) -> dict[str, object]:
    return get_action(request, action_id)


@router.get("/actions/{action_id}/execution")
def get_execution(request: Request, action_id: UUID) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _actions().get_execution(ctx, action_id)


@router.post("/actions/{action_id}/approve")
def approve_action(request: Request, action_id: UUID, body: DecisionBody) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    if not body.confirm:
        raise DomainError("approval confirmation required")
    payload = _approvals().decide(ctx, action_id, "APPROVED", session_bound=True)
    publish_unpublished(db_engine(), queue())
    return payload


@router.post("/actions/{action_id}/reject")
def reject_action(
    request: Request, action_id: UUID, body: DecisionBody | None = None
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _approvals().decide(ctx, action_id, "REJECTED", session_bound=True)


@router.post("/approvals/{action_id}/approve")
def approve_via_contracts(
    request: Request, action_id: UUID, body: DecisionBody
) -> dict[str, object]:
    return approve_action(request, action_id, body)


@router.post("/approvals/{action_id}/reject")
def reject_via_contracts(request: Request, action_id: UUID) -> dict[str, object]:
    return reject_action(request, action_id)
