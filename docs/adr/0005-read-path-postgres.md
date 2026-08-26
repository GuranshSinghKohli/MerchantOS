# ADR 0005 — Agent reads from Postgres

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

Agents need commerce evidence. Calling live Shopify Admin API on every tool hit is slow, rate-limit expensive, hard to evaluate, and easier to leak tokens into the agent layer.

## Decision

Sync workers write a tenant-scoped projection to PostgreSQL. MCP read tools query that projection through repositories. Only sync and the action executor use `ShopifyPort`.

## Alternatives

- Live Shopify on every tool call — rejected for rate limits, latency, and testability
- LLM-facing GraphQL — rejected; unrestricted API access

## Tradeoffs

Data can lag Shopify until sync/webhooks land. We make sync status visible and treat “not yet synced” as insufficient data.

## Consequences

AgentBench can run on fixtures with no Shopify network. Metrics are computed in application code against Postgres.
