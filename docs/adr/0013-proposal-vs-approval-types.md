# ADR 0013 — Proposal vs approval types

- **Status:** Accepted
- **Date:** 2026-08-25
- **Supersedes:** [0007](0007-approval-and-action-state-machines.md) *Safety may insert Approval PENDING*; [0011](0011-approval-gated-mutations.md) *unspecified snapshot authorship*. Two machines remain.

## Context

Review C1, C2, H1, H6, H7: model-authored HITL fields, Safety as an LLM agent, MEDIUM not gated, freeze-after-approve race, `allow` implying Shopify write.

## Decision

1. Agents may produce `AgentActionProposal` only.
2. `PolicyService` (no `LLMPort`) returns `require_approval` | `block`. There is no `allow` for Shopify mutations.
3. MEDIUM and HIGH persist `Action.PROPOSED` and set `AgentRun.WAITING_APPROVAL`. CRITICAL → `Action.BLOCKED`.
4. `ApprovalRecord` is created **only** by `ApprovalService.decide` from `TenantContext.from_session`.
5. `SnapshotService` writes `before_state`, `after_state`, `payload`, `payload_hash` at PROPOSED time from Postgres (and live Shopify read if needed for current price). The model cannot supply these.
6. Merchant approve copies `payload_hash` onto the approval; executor requires match.
7. `ApprovedAction` is loaded from DB; it has no constructor from LLM output.
8. `create_recommendation` does not include `approval_required`.

State machines:

- **Action:** `PROPOSED → APPROVED → QUEUED → EXECUTING → COMPLETED | FAILED` or `PROPOSED → BLOCKED`
- **Approval:** created as `APPROVED` or `REJECTED` at merchant decision time (no agent-created `PENDING` row)
- **AgentRun:** `PENDING → RUNNING → WAITING_APPROVAL | COMPLETED | FAILED | CANCELLED`

## Alternatives

- Safety inserts PENDING approvals — rejected; agents must not create approval rows
- Trust model `before`/`after` and show them in the UI — rejected; HITL theater

## Tradeoffs

Approvals UI lists `Action.PROPOSED` rows, not `Approval.PENDING` rows. Slightly different from the first ERD wording.

## Consequences

`docs/contracts.md` §3–4. Tests listed there are mandatory when domain/app packages land.
