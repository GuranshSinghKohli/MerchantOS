from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from merchantos_domain import (
    TERMINAL_STATUSES,
    AgentRunStatus,
    JobKind,
    TenantContext,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from merchantos_db.ids import uuid7
from merchantos_db.models import AgentRun, OutboxMessage, ToolCallRecord
from merchantos_db.rls import tenant_scope


@dataclass
class AgentRunIdentity:
    merchant_id: UUID
    store_id: UUID
    user_id: UUID | None
    request_id: UUID
    scopes: tuple[str, ...]


class AgentRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        ctx: TenantContext,
        *,
        question: str,
    ) -> AgentRun:
        with tenant_scope(self._session, ctx.merchant_id):
            row = AgentRun(
                id=uuid7(),
                merchant_id=ctx.merchant_id,
                store_id=ctx.store_id,
                user_id=ctx.user_id,
                request_id=ctx.request_id,
                question=question,
                status=AgentRunStatus.PENDING.value,
                scopes=list(ctx.scopes),
            )
            self._session.add(row)
            self._session.add(
                OutboxMessage(
                    merchant_id=ctx.merchant_id,
                    job_kind=JobKind.AGENT_RUN.value,
                    job_id=row.id,
                )
            )
            self._session.flush()
            return row

    def get(self, run_id: UUID) -> AgentRun | None:
        return self._session.get(AgentRun, run_id)

    def get_for_tenant(self, ctx: TenantContext, run_id: UUID) -> AgentRun | None:
        with tenant_scope(self._session, ctx.merchant_id):
            row = self._session.get(AgentRun, run_id)
            if row is None or row.merchant_id != ctx.merchant_id:
                return None
            return row

    def identity(self, run_id: UUID) -> AgentRunIdentity | None:
        row = self.get(run_id)
        if row is None:
            return None
        return AgentRunIdentity(
            merchant_id=row.merchant_id,
            store_id=row.store_id,
            user_id=row.user_id,
            request_id=row.request_id,
            scopes=tuple(row.scopes or ()),
        )

    def list_for_tenant(self, ctx: TenantContext, *, limit: int = 20) -> list[AgentRun]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(AgentRun)
                    .where(
                        AgentRun.merchant_id == ctx.merchant_id,
                        AgentRun.store_id == ctx.store_id,
                    )
                    .order_by(AgentRun.created_at.desc())
                    .limit(limit)
                )
            )

    def acquire_lease(
        self, run_id: UUID, *, owner: str, now: datetime, ttl: timedelta
    ) -> AgentRun | None:
        row = self.get(run_id)
        if row is None:
            return None
        if row.status in {status.value for status in TERMINAL_STATUSES}:
            return None
        if (
            row.status == AgentRunStatus.RUNNING.value
            and row.lease_until is not None
            and row.lease_until > now
            and row.lease_owner is not None
            and row.lease_owner != owner
        ):
            return None
        row.status = AgentRunStatus.RUNNING.value
        row.attempt = row.attempt + 1
        row.lease_owner = owner
        row.lease_until = now + ttl
        if row.started_at is None:
            row.started_at = now
        self._session.flush()
        return row

    def request_cancel(self, ctx: TenantContext, run_id: UUID, *, now: datetime) -> AgentRun | None:
        row = self.get_for_tenant(ctx, run_id)
        if row is None:
            return None
        if row.status == AgentRunStatus.PENDING.value:
            row.status = AgentRunStatus.CANCELLED.value
            row.finished_at = now
            row.error_code = "cancelled"
            row.error_message = "cancelled before start"
            self._session.flush()
        return row

    def complete(
        self,
        run_id: UUID,
        *,
        now: datetime,
        classification: str | None,
        plan: str | None,
        result_json: str,
        token_input: int,
        token_output: int,
        model: str | None,
        latency_ms: int,
        estimated_cost_usd: str | None,
    ) -> None:
        row = self.get(run_id)
        if row is None:
            return
        row.status = AgentRunStatus.COMPLETED.value
        row.classification = classification
        row.plan = plan
        row.result_json = result_json
        row.token_input = token_input
        row.token_output = token_output
        row.model = model
        row.latency_ms = latency_ms
        row.estimated_cost_usd = estimated_cost_usd
        row.finished_at = now
        row.lease_until = None
        row.error_code = None
        row.error_message = None
        self._session.flush()

    def fail(
        self,
        run_id: UUID,
        *,
        now: datetime,
        error_code: str,
        error_message: str,
        latency_ms: int | None = None,
        token_input: int = 0,
        token_output: int = 0,
        model: str | None = None,
    ) -> None:
        row = self.get(run_id)
        if row is None:
            return
        row.status = AgentRunStatus.FAILED.value
        row.error_code = error_code[:80]
        row.error_message = error_message[:500]
        row.finished_at = now
        row.lease_until = None
        if latency_ms is not None:
            row.latency_ms = latency_ms
        row.token_input = token_input
        row.token_output = token_output
        row.model = model
        self._session.flush()

    def record_tool_call(
        self,
        ctx: TenantContext,
        *,
        run_id: UUID,
        tool_name: str,
        permission: str,
        risk_level: str,
        input_redacted: str,
        output_redacted: str,
        status: str,
        latency_ms: int | None,
        error_code: str | None,
    ) -> None:
        with tenant_scope(self._session, ctx.merchant_id):
            self._session.add(
                ToolCallRecord(
                    merchant_id=ctx.merchant_id,
                    run_id=run_id,
                    tool_name=tool_name,
                    permission=permission,
                    risk_level=risk_level,
                    input_redacted=input_redacted,
                    output_redacted=output_redacted,
                    status=status,
                    latency_ms=latency_ms,
                    error_code=error_code,
                )
            )
            self._session.flush()

    def list_tool_calls(self, ctx: TenantContext, run_id: UUID) -> list[ToolCallRecord]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(ToolCallRecord).where(
                        ToolCallRecord.merchant_id == ctx.merchant_id,
                        ToolCallRecord.run_id == run_id,
                    )
                )
            )
