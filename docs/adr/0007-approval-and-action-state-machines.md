# ADR 0007 — Separate approval and action state machines

- **Status:** Superseded by [0013](0013-proposal-vs-approval-types.md)
- **Date:** 2026-08-25

## Context

Boolean flags (`is_approved`, `is_running`) hide illegal transitions. Collapsing approval and execution into one machine lets an agent-shaped writer touch “approved.”

## Decision

Two machines:

- **Approval:** `PENDING → APPROVED | REJECTED | EXPIRED` — written only by the merchant session API (Safety may insert `PENDING`)
- **Action:** `CREATED → APPROVED → QUEUED → EXECUTING → COMPLETED | FAILED` (`BLOCKED` for CRITICAL)

**AgentRun** uses `PENDING → RUNNING → WAITING_APPROVAL | COMPLETED | FAILED | CANCELLED`.

## Alternatives

- Single workflow status — weaker audit and easier self-approval bugs
- Booleans — rejected by design principles §12

## Tradeoffs

More columns and transition tests. Clearer authorization.

## Consequences

Approve and execute are different transactions. Payload is immutable after `Action.APPROVED`. Unapproved execute is a hard error.
