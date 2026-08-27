from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from merchantos_domain import (
    ActionResult,
    ActionStatus,
    JobKind,
    TenantContext,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from merchantos_db.ids import uuid7
from merchantos_db.models import (
    Action,
    ActionResultRow,
    Approval,
    AuditEvent,
    OutboxMessage,
    Product,
)
from merchantos_db.rls import tenant_scope


@dataclass
class ActionIdentity:
    merchant_id: UUID
    store_id: UUID
    user_id: UUID | None
    request_id: UUID
    scopes: tuple[str, ...]


class ActionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_product(self, ctx: TenantContext, product_id: UUID) -> Product | None:
        with tenant_scope(self._session, ctx.merchant_id):
            row = self._session.get(Product, product_id)
            if row is None or row.merchant_id != ctx.merchant_id or row.store_id != ctx.store_id:
                return None
            if row.deleted_at is not None:
                return None
            return row

    def insert_proposed(
        self,
        ctx: TenantContext,
        *,
        action_type: str,
        status: str,
        risk_level: str,
        resource_id: UUID,
        resource_gid: str,
        rationale: str,
        evidence_json: str,
        source_recommendation_id: str | None,
        payload_json: str,
        payload_hash: str,
        before_state_json: str,
        after_state_json: str,
        idempotency_key: str,
        expires_at: datetime,
    ) -> Action:
        with tenant_scope(self._session, ctx.merchant_id):
            existing = self._session.scalar(
                select(Action).where(
                    Action.merchant_id == ctx.merchant_id,
                    Action.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return existing
            row = Action(
                id=uuid7(),
                merchant_id=ctx.merchant_id,
                store_id=ctx.store_id,
                user_id=ctx.user_id,
                request_id=ctx.request_id,
                scopes=list(ctx.scopes),
                action_type=action_type,
                status=status,
                risk_level=risk_level,
                resource_id=resource_id,
                resource_gid=resource_gid,
                rationale=rationale,
                evidence_json=evidence_json,
                source_recommendation_id=source_recommendation_id,
                payload_json=payload_json,
                payload_hash=payload_hash,
                before_state_json=before_state_json,
                after_state_json=after_state_json,
                idempotency_key=idempotency_key,
                expires_at=expires_at,
            )
            self._session.add(row)
            self._session.flush()
            return row

    def get_for_tenant(self, ctx: TenantContext, action_id: UUID) -> Action | None:
        with tenant_scope(self._session, ctx.merchant_id):
            row = self._session.get(Action, action_id)
            if row is None or row.merchant_id != ctx.merchant_id or row.store_id != ctx.store_id:
                return None
            return row

    def get(self, action_id: UUID) -> Action | None:
        return self._session.get(Action, action_id)

    def identity(self, action_id: UUID) -> ActionIdentity | None:
        row = self.get(action_id)
        if row is None:
            return None
        return ActionIdentity(
            merchant_id=row.merchant_id,
            store_id=row.store_id,
            user_id=row.user_id,
            request_id=row.request_id,
            scopes=tuple(row.scopes or ()),
        )

    def list_for_tenant(self, ctx: TenantContext, *, limit: int = 40) -> list[Action]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(Action)
                    .where(
                        Action.merchant_id == ctx.merchant_id,
                        Action.store_id == ctx.store_id,
                    )
                    .order_by(Action.created_at.desc())
                    .limit(limit)
                )
            )

    def get_approval(self, ctx: TenantContext, action_id: UUID) -> Approval | None:
        with tenant_scope(self._session, ctx.merchant_id):
            return self._session.scalar(
                select(Approval).where(
                    Approval.merchant_id == ctx.merchant_id,
                    Approval.action_id == action_id,
                )
            )

    def insert_approval(
        self,
        ctx: TenantContext,
        *,
        action_id: UUID,
        status: str,
        frozen_payload_hash: str,
        risk_level: str,
        decided_by: UUID,
        decided_at: datetime,
    ) -> Approval:
        with tenant_scope(self._session, ctx.merchant_id):
            row = Approval(
                id=uuid7(),
                merchant_id=ctx.merchant_id,
                action_id=action_id,
                status=status,
                frozen_payload_hash=frozen_payload_hash,
                risk_level=risk_level,
                decided_by=decided_by,
                decided_at=decided_at,
            )
            self._session.add(row)
            self._session.flush()
            return row

    def set_status(self, action_id: UUID, status: str, *, now: datetime | None = None) -> None:
        row = self.get(action_id)
        if row is None:
            return
        row.status = status
        if status in {
            ActionStatus.COMPLETED.value,
            ActionStatus.FAILED.value,
            ActionStatus.REJECTED.value,
            ActionStatus.EXPIRED.value,
            ActionStatus.CONFLICT.value,
            ActionStatus.BLOCKED.value,
        }:
            row.finished_at = now
        self._session.flush()

    def enqueue_execution(self, ctx: TenantContext, action_id: UUID) -> None:
        with tenant_scope(self._session, ctx.merchant_id):
            self._session.add(
                OutboxMessage(
                    merchant_id=ctx.merchant_id,
                    job_kind=JobKind.ACTION_EXECUTE.value,
                    job_id=action_id,
                )
            )
            self._session.flush()

    def acquire_lease(
        self, action_id: UUID, *, owner: str, now: datetime, ttl: timedelta
    ) -> Action | None:
        row = self.get(action_id)
        if row is None:
            return None
        if row.status in {
            ActionStatus.COMPLETED.value,
            ActionStatus.FAILED.value,
            ActionStatus.REJECTED.value,
            ActionStatus.EXPIRED.value,
            ActionStatus.CONFLICT.value,
            ActionStatus.BLOCKED.value,
        }:
            return None
        if (
            row.status == ActionStatus.EXECUTING.value
            and row.lease_until is not None
            and row.lease_until > now
            and row.lease_owner is not None
            and row.lease_owner != owner
        ):
            return None
        row.status = ActionStatus.EXECUTING.value
        row.attempt = row.attempt + 1
        row.lease_owner = owner
        row.lease_until = now + ttl
        self._session.flush()
        return row

    def record_result(self, ctx: TenantContext, action_id: UUID, result: ActionResult) -> None:
        with tenant_scope(self._session, ctx.merchant_id):
            existing = self._session.scalar(
                select(ActionResultRow).where(
                    ActionResultRow.merchant_id == ctx.merchant_id,
                    ActionResultRow.action_id == action_id,
                )
            )
            if existing is not None:
                return
            self._session.add(
                ActionResultRow(
                    merchant_id=ctx.merchant_id,
                    action_id=action_id,
                    ok=result.ok,
                    mutation_name=result.mutation_name,
                    shopify_request_id=result.shopify_request_id,
                    error_code=result.error_code,
                    verified=result.verified,
                    before_state_json=json.dumps(result.before_state),
                    after_state_json=json.dumps(result.after_state),
                    response_redacted=json.dumps(result.response_redacted),
                )
            )
            self._session.flush()

    def get_result(self, ctx: TenantContext, action_id: UUID) -> ActionResultRow | None:
        with tenant_scope(self._session, ctx.merchant_id):
            return self._session.scalar(
                select(ActionResultRow).where(
                    ActionResultRow.merchant_id == ctx.merchant_id,
                    ActionResultRow.action_id == action_id,
                )
            )

    def fail(
        self,
        action_id: UUID,
        *,
        now: datetime,
        error_code: str,
        error_message: str,
        status: str = ActionStatus.FAILED.value,
    ) -> None:
        row = self.get(action_id)
        if row is None:
            return
        row.status = status
        row.error_code = error_code[:80]
        row.error_message = error_message[:500]
        row.finished_at = now
        row.lease_until = None
        self._session.flush()

    def write_audit(
        self,
        ctx: TenantContext,
        *,
        event_type: str,
        action_id: UUID,
        actor_type: str,
        actor_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        with tenant_scope(self._session, ctx.merchant_id):
            self._session.add(
                AuditEvent(
                    merchant_id=ctx.merchant_id,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    request_id=str(ctx.request_id),
                    event_type=event_type,
                    resource_type="action",
                    resource_id=str(action_id),
                    metadata_json=json.dumps(metadata),
                )
            )
            self._session.flush()

    def list_audit(self, ctx: TenantContext, action_id: UUID) -> list[AuditEvent]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.merchant_id == ctx.merchant_id,
                        AuditEvent.resource_type == "action",
                        AuditEvent.resource_id == str(action_id),
                    )
                    .order_by(AuditEvent.created_at.asc())
                )
            )

    def update_product_projection(
        self,
        ctx: TenantContext,
        product_id: UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
    ) -> None:
        with tenant_scope(self._session, ctx.merchant_id):
            row = self._session.get(Product, product_id)
            if row is None or row.merchant_id != ctx.merchant_id:
                return
            if title is not None:
                row.title = title
            if description is not None:
                row.description = description
            if tags is not None:
                row.tags = tags
            if status is not None:
                row.status = status
            self._session.flush()
