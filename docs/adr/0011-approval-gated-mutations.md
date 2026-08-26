# ADR 0011 — Approval-gated Shopify mutations

- **Status:** Superseded by [0013](0013-proposal-vs-approval-types.md) and [0016](0016-deterministic-action-snapshots.md) for types and snapshots. The “no unapproved Shopify write” decision remains.
- **Date:** 2026-08-25

## Context

Autonomous price or discount changes can harm a merchant. The PRD and design principles forbid the agent, the frontend, or the LLM from executing Shopify mutations.

## Decision

Meaningful Shopify writes follow:

```
typed proposal → deterministic risk → Safety → merchant approval → executor → audit
```

HIGH requires explicit approval. CRITICAL (deletes, bulk mutations) is blocked in V1. Risk is assigned from action type and blast radius in code. The executor checks database approval state, not agent memory.

## Alternatives

- Auto-execute LOW/MEDIUM Shopify writes — rejected for V1 product risk
- LLM self-scored risk — rejected; model is not the authority

## Tradeoffs

The demo has an extra human step. That step is the product.

## Consequences

Approval UI must show action, reason, evidence, resources, before/after, impact, risk, permissions, rollback, and expiry. `execute_approved_action` is not an orchestrator tool.
