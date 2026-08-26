# ADR 0014 — Tenant context from job row only

- **Status:** Accepted
- **Date:** 2026-08-25
- **Supersedes:** [0009](0009-server-injected-tenant-context.md) *worker job payload as a tenant source*. Session-based context for HTTP remains.

## Context

Review H3: ADR 0009 allowed `TenantContext` from the worker job payload. A forged or buggy SQS message could switch tenants if the worker trusted that body.

## Decision

- HTTP: `TenantContext.from_session(session_row)`.
- Async: queue body is `{job_kind, job_id, traceparent?}`. Worker loads the row (`agent_runs`, `sync_jobs`, `actions`, `webhook_events`) and calls `TenantContext.from_job_row(row)`.
- No factory from tool args, agent state, LLM output, or queue JSON tenant fields.
- Extra tenant fields on a message are ignored and logged as a contract violation.

## Alternatives

- Sign the queue payload including merchant_id — still duplicates truth; the row is enough
- Trust the producer — rejected

## Tradeoffs

One extra DB read per job. Required.

## Consequences

`docs/contracts.md` §2. Contract test: building context from a queue body fails.
