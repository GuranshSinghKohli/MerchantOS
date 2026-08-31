# ADR 0027 — Phase 12 productization on existing APIs

- **Status:** Accepted
- **Date:** 2026-08-31
- **Related:** [0019](0019-frontend-ui-stack.md), [0023](0023-phase9-human-approved-mutations.md), [0026](0026-phase11-eval-and-hardening.md)

## Context

Phases 1–11 shipped Ask, intelligence, sync, and approval APIs. The dashboard did not expose Ask MerchantOS, treated an unsynced store as zero-order KPIs, and used install copy that was technically accurate but thin for a demo.

## Decision

- Add an **Ask MerchantOS** screen that calls existing `POST /api/v1/intelligence/query` and polls the existing run. No new agent graph.
- Empty Overview uses `store.sync_status === not_started` to hide zero KPIs and offer **Import store data** via existing `POST /api/v1/store/sync`.
- Merchant-facing copy hides GraphQL GIDs, tool names, and run internals. Evidence facts remain visible.
- Production AWS apply remains operator-gated. No new AWS services.

## Alternatives

- Fake dashboard numbers for screenshots — rejected (violates SYSTEM_DESIGN and Phase 12 demo rules)
- New execute or chat architecture — rejected

## Consequences

- Demo script (`docs/demo.md`) documents the live path and the empty-store fallback
- README and `docs/FINAL_RELEASE.md` describe the shipped product, not a later phase
