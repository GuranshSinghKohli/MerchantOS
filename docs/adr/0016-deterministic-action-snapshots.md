# ADR 0016 — Deterministic action snapshots

- **Status:** Accepted
- **Date:** 2026-08-25
- **Supersedes:** [0011](0011-approval-gated-mutations.md) *unspecified authorship of before/after and approval_required*. Approval-gated Shopify writes remain.

## Context

Review C1: `create_action_plan` could persist model-written params/before/after; `create_recommendation` accepted `approval_required`.

## Decision

`SnapshotService` (application service, no LLM) loads current variant/discount state from the tenant-scoped projection (refreshing from Shopify read if the snapshot is stale) and builds:

- `before_state`
- `after_state` (typed function of `ActionType` + current state, not free-form model JSON)
- `payload` (allowlisted fields per `ActionType`)
- `payload_hash`

The planner supplies only `action_type`, `resource_ids`, `rationale`, `evidence_refs`.

`approval_required` is not a stored recommendation field. PolicyService owns that decision.

## Alternatives

- Show model text as before/after and hope the merchant notices — rejected

## Tradeoffs

Planner cannot invent a custom mutation shape. That is the point.

## Consequences

`docs/mcp.md` tool I/O updated. Tests: mutating `after_state` in a fake LLM output does not change the persisted snapshot.
