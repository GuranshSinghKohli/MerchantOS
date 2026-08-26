# ADR 0020 — Analytics computed on read from the commerce projection

- **Status:** Accepted
- **Date:** 2026-08-26
- **Does not supersede** [0005](0005-read-path-postgres.md)

## Context

Phase 4 needs merchant KPIs. `docs/database.md` describes a derived `metrics` table for later grains. Materializing that table now would duplicate Phase 3 commerce data and add a job we do not have.

## Decision

Compute analytics **on read** from `orders`, `order_lines`, `products`, `variants`, `customers`, and `inventory_snapshots` using tenant-scoped SQL aggregation. Do not add a `metrics` table in Phase 4.

Indexes added only for these query patterns: `(merchant_id, store_id, processed_at)` on orders, `(merchant_id, first_order_at)` on customers, `(merchant_id, order_id)` on order_lines.

No Redis cache. TanStack Query keys include the trusted `store_id` from `GET /api/v1/me` plus date-range filters. They never include a client-supplied tenant id.

## Alternatives

- Nightly `metrics` rollup — rejected until query cost is measured
- Compute in Python after `SELECT *` — rejected (N+1 / full-table load)

## Consequences

`docs/metrics.md`. Revisit a rollup table if overview latency becomes a problem.
