# ADR 0022 — Intelligence reuses AgentRun with run_kind

- **Status:** Accepted
- **Date:** 2026-08-26
- **Does not change** [0012](0012-capability-isolated-workers.md) (no execute tool), [0013](0013-proposal-vs-approval-types.md) (proposal vs approval), [0014](0014-tenant-from-job-row.md) (trusted tenant), or [0008](0008-llm-provider-port.md) (LLMPort)

## Context

Phase 8 needs a persisted intelligence run, selected specialists, findings, evidence, recommendations, contradictions, status, latency, and errors. A new `intelligence_runs` table and worker kind would duplicate the Phase 6 outbox, lease, and tool-call machinery.

## Decision

1. Reuse `agent_runs` with `run_kind` = `ask` | `intelligence`.
2. Keep one `job_kind=agent_run` outbox message. The worker branches on `run_kind`.
3. Persist `IntelligenceReport` JSON in `result_json`. Public reports omit tenant ids, tokens, and graph internals.
4. `POST /api/v1/intelligence/query` cannot specify agent class names.

The LLM may synthesize and recommend. Deterministic code selects allowlisted specialists, extracts evidence, detects contradictions, clamps confidence/priority, and drops execute/approve recommendations.

## Alternatives

- New `intelligence_runs` table — rejected; duplicates leases, outbox, and tool-call persistence
- Let the model choose arbitrary agent classes — rejected; unbounded and unsafe
- Persist raw LLM transcripts — rejected; unnecessary PII and prompt leakage

## Tradeoffs

Ask and intelligence share one worker handler. List/get APIs filter by `run_kind` so the surfaces stay separate.

## Consequences

Alembic `0007_phase8`. Update `docs/agents.md`, `docs/database.md`, and `docs/architecture.md`. Do not start approvals or Shopify mutations.
