# ADR 0023 — Phase 9 human-approved product mutations

- **Status:** Accepted
- **Date:** 2026-08-26
- **Extends:** [0013](0013-proposal-vs-approval-types.md), [0016](0016-deterministic-action-snapshots.md), [0012](0012-capability-isolated-workers.md)

## Context

Phase 8 intelligence may recommend. It must not approve, construct `ApprovedAction`, or call Shopify. Phase 9 introduces the merchant-approved write path for a deliberately narrow product-metadata allowlist.

The Phase 9 product brief names extra terminal states (`REJECTED`, `EXPIRED`, `CONFLICT`) that ADR 0013 did not list. Those states are added here without converting a proposal into an approved action.

## Decision

1. Executable action types are only:
   - `update_product_title`
   - `update_product_description`
   - `update_product_tags`
   - `update_product_status` (`ACTIVE` | `DRAFT` only)
2. `update_variant_price` and `reduce_discount_depth` remain on `ActionType` as HIGH/CRITICAL and are **blocked**. No mutator exists for them.
3. Action machine: `PROPOSED → APPROVED → QUEUED → EXECUTING → COMPLETED | FAILED`, or `PROPOSED → BLOCKED | REJECTED | EXPIRED`, or `EXECUTING → CONFLICT | EXPIRED | FAILED`.
4. Approval rows are created only by `ApprovalService.decide(..., session_bound=True)` from `TenantContext.from_session` as `APPROVED` or `REJECTED`.
5. `ApprovedAction` has no public constructor and no `model_validate`. The worker loads it after DB checks.
6. Approval HTTP paths `POST /api/v1/actions/{id}/approve` and `POST /api/v1/approvals/{action_id}/approve` call the same service. Tenant comes from the session cookie.
7. Execution is asynchronous: approve writes `QUEUED` + outbox `{job_kind=action_execute, job_id}` in one transaction. The HTTP handler does not call Shopify.
8. All Shopify writes go through typed `ShopifyMutator` methods. There is no generic GraphQL/HTTP execute helper on the protocol.
9. Install scopes include `write_products`. Price, discount, order, and customer write scopes stay omitted.
10. Intelligence still stops at `Recommendation`. Merchants create proposals via `POST /api/v1/actions` with server-built snapshots.

## Alternatives

- Auto-approve LOW product edits — rejected; SYSTEM_DESIGN says LOW never writes Shopify, and product metadata is MEDIUM.
- Generic `execute_shopify_request` — rejected; arbitrary Admin API access is out of V1.
- Agent-created `Approval.PENDING` — already rejected by ADR 0013.

## Tradeoffs

Existing installs must re-auth to receive `write_products`. Description is stored on the local product projection after a successful mutation; catalog sync does not yet persist Shopify description HTML.

## Consequences

`docs/contracts.md`, `docs/security.md`, `docs/database.md`, and `docs/architecture.md` record the extra states and executable types. Tests must prove the LLM cannot approve or execute.
