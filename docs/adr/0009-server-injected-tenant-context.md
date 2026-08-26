# ADR 0009 — Server-injected tenant context

- **Status:** Superseded by [0014](0014-tenant-from-job-row.md) for the async tenant source. HTTP session factory remains valid.
- **Date:** 2026-08-25

## Context

If a tool or query trusts `tenant_id` from the model, prompt injection or a confused agent can cross tenants.

## Decision

`TenantContext` is created from the authenticated session (or the worker’s job payload, which was written by that session). The MCP runtime injects it and strips any model-supplied tenant fields. Repositories refuse queries without it. RLS is defense in depth.

## Alternatives

- Pass tenant id as a tool argument — rejected
- RLS only — insufficient if a query forgets the session variable

## Tradeoffs

Every repository method takes `TenantContext`. That is intentional friction.

## Consequences

Foreign ids return 404. Two-merchant tests are required for merchant data APIs. Agents cannot “select” another store.
