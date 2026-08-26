from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from merchantos_agents import run_orchestrator, to_ask_result
from merchantos_db import AgentRunRepository, session_scope
from merchantos_domain import (
    MAX_AGENT_ATTEMPTS,
    TERMINAL_STATUSES,
    InvalidModelOutputError,
    LLMTimeoutError,
    ProviderFailureError,
    TenantContext,
    TransientJobError,
)
from merchantos_llm import LLMPort
from merchantos_mcp import ToolError, ToolErrorCode, ToolRegistry
from merchantos_observability import get_logger, redact_mapping
from sqlalchemy import Engine

from merchantos_worker.capabilities import AgentCapabilities

logger = get_logger(__name__)
_LEASE = timedelta(seconds=45)


def handle_agent_run(
    *,
    engine: Engine,
    caps: AgentCapabilities,
    job_id: UUID,
    owner: str,
) -> None:
    now = datetime.now(UTC)
    with session_scope(engine) as db:
        repo = AgentRunRepository(db)
        existing = repo.get(job_id)
        if existing is None:
            return
        if existing.status in {status.value for status in TERMINAL_STATUSES}:
            return
        identity = repo.identity(job_id)
        row = repo.acquire_lease(job_id, owner=owner, now=now, ttl=_LEASE)
        if row is None or identity is None:
            return
        attempt = row.attempt
        question = row.question
        run_id = row.id
    ctx = TenantContext.from_job_row(identity)
    started = time.perf_counter()
    recorded: list[tuple[str, dict[str, Any], Any, int]] = []

    def recorder(name: str, arguments: dict[str, Any], result: Any, latency_ms: int) -> None:
        recorded.append((name, arguments, result, latency_ms))

    try:
        state = run_orchestrator(
            llm=caps.llm,
            tools=caps.tools,
            tenant=ctx,
            run_id=run_id,
            request_id=ctx.request_id,
            question=question,
            recorder=recorder,
        )
        result = to_ask_result(state)
        latency_ms = int((time.perf_counter() - started) * 1000)
        with session_scope(engine) as db:
            runs = AgentRunRepository(db)
            runs.complete(
                run_id,
                now=datetime.now(UTC),
                classification=state.classification,
                plan=state.plan,
                result_json=result.model_dump_json(),
                token_input=state.token_input,
                token_output=state.token_output,
                model=state.model,
                latency_ms=latency_ms,
                estimated_cost_usd="0",
            )
            _persist_tools(runs, ctx, run_id, recorded)
        logger.info(
            "agent_run_completed",
            run_id=str(run_id),
            request_id=str(ctx.request_id),
            merchant_id=str(ctx.merchant_id),
            store_id=str(ctx.store_id),
            agent_name=state.agent_name or "orchestrator",
            duration_ms=latency_ms,
            success=True,
            retry_count=attempt,
            model=state.model,
            token_input=state.token_input,
            token_output=state.token_output,
        )
    except (LLMTimeoutError, ProviderFailureError, ToolError) as exc:
        _fail_or_retry(
            engine,
            run_id=run_id,
            ctx=ctx,
            attempt=attempt,
            started=started,
            exc=exc,
            recorded=recorded,
            retryable=_retryable(exc),
        )
    except InvalidModelOutputError as exc:
        _fail_or_retry(
            engine,
            run_id=run_id,
            ctx=ctx,
            attempt=attempt,
            started=started,
            exc=exc,
            recorded=recorded,
            retryable=False,
        )


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, ToolError):
        return exc.code in {ToolErrorCode.TIMEOUT, ToolErrorCode.DEPENDENCY_FAILURE}
    return isinstance(exc, TransientJobError)


def _fail_or_retry(
    engine: Engine,
    *,
    run_id: UUID,
    ctx: TenantContext,
    attempt: int,
    started: float,
    exc: Exception,
    recorded: list[tuple[str, dict[str, Any], Any, int]],
    retryable: bool,
) -> None:
    latency_ms = int((time.perf_counter() - started) * 1000)
    code = getattr(getattr(exc, "code", None), "value", None) or type(exc).__name__
    if retryable and attempt < MAX_AGENT_ATTEMPTS:
        logger.warning(
            "agent_run_retry",
            run_id=str(run_id),
            request_id=str(ctx.request_id),
            error_category=code,
            retry_count=attempt,
        )
        raise TransientJobError("agent run will retry") from exc
    with session_scope(engine) as db:
        runs = AgentRunRepository(db)
        runs.fail(
            run_id,
            now=datetime.now(UTC),
            error_code=str(code)[:80],
            error_message="agent run failed",
            latency_ms=latency_ms,
        )
        _persist_tools(runs, ctx, run_id, recorded)
    logger.info(
        "agent_run_failed",
        run_id=str(run_id),
        request_id=str(ctx.request_id),
        merchant_id=str(ctx.merchant_id),
        duration_ms=latency_ms,
        success=False,
        error_category=code,
        retry_count=attempt,
    )


def _persist_tools(
    runs: AgentRunRepository,
    ctx: TenantContext,
    run_id: UUID,
    recorded: list[tuple[str, dict[str, Any], Any, int]],
) -> None:
    for name, arguments, result, latency_ms in recorded:
        try:
            from merchantos_mcp.allowlists import TOOL_PERMISSION

            permission = TOOL_PERMISSION[name].value
        except KeyError:
            permission = "unknown"
        runs.record_tool_call(
            ctx,
            run_id=run_id,
            tool_name=name,
            permission=permission,
            risk_level="LOW",
            input_redacted=json.dumps(redact_mapping(arguments)),
            output_redacted=json.dumps(redact_mapping(getattr(result, "output", {}) or {})),
            status="ok" if getattr(result, "ok", False) else "error",
            latency_ms=latency_ms,
            error_code=getattr(result, "error_code", None),
        )


def build_agent_capabilities(llm: LLMPort, tools: ToolRegistry) -> AgentCapabilities:
    return AgentCapabilities(tools=tools, llm=llm)
