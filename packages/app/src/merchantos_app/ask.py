from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from merchantos_db import AgentRunRepository, session_scope
from merchantos_db.models import AgentRun
from merchantos_domain import (
    MAX_QUESTION_CHARS,
    AgentCancelledError,
    AgentRunStatus,
    DomainError,
    NotFoundError,
    TenantContext,
)
from sqlalchemy import Engine


def _public(row: AgentRun) -> dict[str, object]:
    result = json.loads(row.result_json) if row.result_json else None
    return {
        "run_id": str(row.id),
        "status": row.status,
        "question": row.question,
        "classification": row.classification,
        "result": result,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "latency_ms": row.latency_ms,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


class AskService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def enqueue(self, ctx: TenantContext, question: str) -> dict[str, object]:
        cleaned = question.strip()
        if not cleaned:
            raise DomainError("question is required")
        if len(cleaned) > MAX_QUESTION_CHARS:
            raise DomainError(f"question cannot exceed {MAX_QUESTION_CHARS} characters")
        with session_scope(self._engine) as db:
            row = AgentRunRepository(db).enqueue(ctx, question=cleaned)
            return _public(row)

    def get(self, ctx: TenantContext, run_id: UUID) -> dict[str, object]:
        with session_scope(self._engine) as db:
            row = AgentRunRepository(db).get_for_tenant(ctx, run_id)
            if row is None:
                raise NotFoundError("agent run not found")
            return _public(row)

    def list_runs(self, ctx: TenantContext) -> list[dict[str, object]]:
        with session_scope(self._engine) as db:
            return [_public(row) for row in AgentRunRepository(db).list_for_tenant(ctx)]

    def cancel(self, ctx: TenantContext, run_id: UUID) -> dict[str, object]:
        with session_scope(self._engine) as db:
            row = AgentRunRepository(db).request_cancel(ctx, run_id, now=datetime.now(UTC))
            if row is None:
                raise NotFoundError("agent run not found")
            if row.status != AgentRunStatus.CANCELLED.value:
                raise AgentCancelledError("run cannot be cancelled after it has started")
            return _public(row)
