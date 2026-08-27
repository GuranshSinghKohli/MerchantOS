from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from merchantos_db import ActionRepository, session_scope
from merchantos_db.models import Action
from merchantos_domain import (
    ACTION_TTL_HOURS,
    EXECUTABLE_ACTION_TYPES,
    ActionExpiredError,
    ActionStatus,
    ActionType,
    AgentActionProposal,
    ApprovalStatus,
    AuditEventType,
    DomainError,
    ForbiddenFactoryError,
    IntendedProductChange,
    InvalidActionError,
    NotFoundError,
    TenantContext,
    UnauthorizedError,
)
from sqlalchemy import Engine

from merchantos_app.policy import PolicyService
from merchantos_app.snapshots import SnapshotService


def _public(row: Action, *, approval_status: str | None = None) -> dict[str, object]:
    return {
        "action_id": str(row.id),
        "status": row.status,
        "action_type": row.action_type,
        "risk_level": row.risk_level,
        "title": _title(row),
        "rationale": row.rationale,
        "resource": {
            "id": str(row.resource_id),
            "gid": row.resource_gid,
        },
        "before_state": json.loads(row.before_state_json),
        "after_state": json.loads(row.after_state_json),
        "evidence": json.loads(row.evidence_json),
        "source_recommendation_id": row.source_recommendation_id,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "approval_status": approval_status,
        "error_code": row.error_code,
        "error_message": row.error_message,
    }


def _title(row: Action) -> str:
    after = json.loads(row.after_state_json)
    kind = row.action_type
    if kind == ActionType.UPDATE_PRODUCT_TITLE.value:
        return f"Update product title to “{after.get('title', '')}”"
    if kind == ActionType.UPDATE_PRODUCT_DESCRIPTION.value:
        return "Update product description"
    if kind == ActionType.UPDATE_PRODUCT_TAGS.value:
        return "Update product tags"
    if kind == ActionType.UPDATE_PRODUCT_STATUS.value:
        return f"Set product status to {after.get('status', '')}"
    return kind


class ActionService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._policy = PolicyService()
        self._snapshots = SnapshotService()

    def propose(
        self,
        ctx: TenantContext,
        *,
        action_type: ActionType,
        resource_id: UUID,
        intended: IntendedProductChange,
        rationale: str,
        evidence_refs: list[dict[str, str]] | None = None,
        source_recommendation_id: str | None = None,
    ) -> dict[str, object]:
        if ctx.user_id is None:
            raise UnauthorizedError("merchant session required")
        if action_type.value not in EXECUTABLE_ACTION_TYPES:
            raise InvalidActionError("action type is not allowed")
        proposal = AgentActionProposal(
            action_type=action_type,
            resource_ids=(resource_id,),
            rationale=rationale,
            evidence_refs=tuple(),
        )
        now = datetime.now(UTC)
        with session_scope(self._engine) as db:
            repo = ActionRepository(db)
            product = repo.get_product(ctx, resource_id)
            if product is None:
                raise NotFoundError("product not found")
            snapshot = self._snapshots.build(
                action_type=action_type, product=product, intended=intended
            )
            decision = self._policy.evaluate(ctx, proposal, snapshot)
            expires = now + timedelta(hours=ACTION_TTL_HOURS)
            idem = f"{action_type.value}:{product.id}:{snapshot.payload_hash}"
            status = (
                ActionStatus.BLOCKED.value
                if decision.verdict == "block"
                else ActionStatus.PROPOSED.value
            )
            row = repo.insert_proposed(
                ctx,
                action_type=action_type.value,
                status=status,
                risk_level=decision.risk_level.value,
                resource_id=product.id,
                resource_gid=product.shopify_gid,
                rationale=rationale,
                evidence_json=json.dumps(evidence_refs or []),
                source_recommendation_id=source_recommendation_id,
                payload_json=json.dumps(snapshot.payload),
                payload_hash=snapshot.payload_hash,
                before_state_json=json.dumps(snapshot.before_state),
                after_state_json=json.dumps(snapshot.after_state),
                idempotency_key=idem,
                expires_at=expires,
            )
            repo.write_audit(
                ctx,
                event_type=AuditEventType.ACTION_CREATED.value,
                action_id=row.id,
                actor_type="user",
                actor_id=str(ctx.user_id),
                metadata={
                    "action_type": action_type.value,
                    "risk_level": decision.risk_level.value,
                },
            )
            repo.write_audit(
                ctx,
                event_type=(
                    AuditEventType.ACTION_BLOCKED.value
                    if decision.verdict == "block"
                    else AuditEventType.ACTION_VALIDATED.value
                ),
                action_id=row.id,
                actor_type="system",
                actor_id=None,
                metadata={"verdict": decision.verdict, "reasons": list(decision.reasons)},
            )
            if row.status == ActionStatus.PROPOSED.value:
                repo.write_audit(
                    ctx,
                    event_type=AuditEventType.ACTION_APPROVAL_REQUESTED.value,
                    action_id=row.id,
                    actor_type="system",
                    actor_id=None,
                    metadata={},
                )
            return _public(row)

    def list_actions(
        self, ctx: TenantContext, *, statuses: frozenset[str] | None = None
    ) -> list[dict[str, object]]:
        with session_scope(self._engine) as db:
            repo = ActionRepository(db)
            rows = []
            for row in repo.list_for_tenant(ctx):
                if statuses is not None and row.status not in statuses:
                    continue
                approval = repo.get_approval(ctx, row.id)
                rows.append(_public(row, approval_status=approval.status if approval else None))
            return rows

    def get(self, ctx: TenantContext, action_id: UUID) -> dict[str, object]:
        with session_scope(self._engine) as db:
            repo = ActionRepository(db)
            row = repo.get_for_tenant(ctx, action_id)
            if row is None:
                raise NotFoundError("action not found")
            approval = repo.get_approval(ctx, action_id)
            return _public(row, approval_status=approval.status if approval else None)

    def get_execution(self, ctx: TenantContext, action_id: UUID) -> dict[str, object]:
        with session_scope(self._engine) as db:
            repo = ActionRepository(db)
            row = repo.get_for_tenant(ctx, action_id)
            if row is None:
                raise NotFoundError("action not found")
            result = repo.get_result(ctx, action_id)
            events = [
                {
                    "event_type": item.event_type,
                    "actor_type": item.actor_type,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "metadata": json.loads(item.metadata_json or "{}"),
                }
                for item in repo.list_audit(ctx, action_id)
            ]
            body: dict[str, object] = {
                "action_id": str(row.id),
                "status": row.status,
                "error_code": row.error_code,
                "events": events,
            }
            if result is not None:
                body["result"] = {
                    "ok": result.ok,
                    "mutation_name": result.mutation_name,
                    "verified": result.verified,
                    "error_code": result.error_code,
                    "shopify_request_id": result.shopify_request_id,
                    "before_state": json.loads(result.before_state_json),
                    "after_state": json.loads(result.after_state_json),
                }
            return body


class ApprovalService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def decide(
        self,
        ctx: TenantContext,
        action_id: UUID,
        decision: str,
        *,
        session_bound: bool,
    ) -> dict[str, object]:
        if not session_bound:
            raise ForbiddenFactoryError("approval requires a merchant session")
        if ctx.user_id is None:
            raise UnauthorizedError("merchant session required")
        if decision not in {"APPROVED", "REJECTED"}:
            raise DomainError("invalid decision")
        now = datetime.now(UTC)
        with session_scope(self._engine) as db:
            repo = ActionRepository(db)
            row = repo.get_for_tenant(ctx, action_id)
            if row is None:
                raise NotFoundError("action not found")
            existing = repo.get_approval(ctx, action_id)
            if existing is not None:
                if existing.status == decision:
                    return _public(row, approval_status=existing.status)
                raise DomainError("action already decided")
            if row.status == ActionStatus.EXPIRED.value or row.expires_at <= now:
                repo.set_status(row.id, ActionStatus.EXPIRED.value, now=now)
                repo.write_audit(
                    ctx,
                    event_type=AuditEventType.ACTION_EXPIRED.value,
                    action_id=row.id,
                    actor_type="system",
                    actor_id=None,
                    metadata={},
                )
                raise ActionExpiredError("action has expired")
            if row.status != ActionStatus.PROPOSED.value:
                raise DomainError("action is not awaiting approval")
            if decision == "REJECTED":
                repo.insert_approval(
                    ctx,
                    action_id=row.id,
                    status=ApprovalStatus.REJECTED.value,
                    frozen_payload_hash=row.payload_hash,
                    risk_level=row.risk_level,
                    decided_by=ctx.user_id,
                    decided_at=now,
                )
                repo.set_status(row.id, ActionStatus.REJECTED.value, now=now)
                repo.write_audit(
                    ctx,
                    event_type=AuditEventType.ACTION_REJECTED.value,
                    action_id=row.id,
                    actor_type="user",
                    actor_id=str(ctx.user_id),
                    metadata={},
                )
                row = repo.get_for_tenant(ctx, action_id)
                assert row is not None
                return _public(row, approval_status=ApprovalStatus.REJECTED.value)
            repo.insert_approval(
                ctx,
                action_id=row.id,
                status=ApprovalStatus.APPROVED.value,
                frozen_payload_hash=row.payload_hash,
                risk_level=row.risk_level,
                decided_by=ctx.user_id,
                decided_at=now,
            )
            repo.set_status(row.id, ActionStatus.APPROVED.value, now=now)
            repo.set_status(row.id, ActionStatus.QUEUED.value, now=now)
            repo.enqueue_execution(ctx, row.id)
            repo.write_audit(
                ctx,
                event_type=AuditEventType.ACTION_APPROVED.value,
                action_id=row.id,
                actor_type="user",
                actor_id=str(ctx.user_id),
                metadata={"payload_hash": row.payload_hash},
            )
            repo.write_audit(
                ctx,
                event_type=AuditEventType.ACTION_QUEUED.value,
                action_id=row.id,
                actor_type="system",
                actor_id=None,
                metadata={},
            )
            row = repo.get_for_tenant(ctx, action_id)
            assert row is not None
            return _public(row, approval_status=ApprovalStatus.APPROVED.value)
