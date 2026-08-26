# ADR 0001 — Monorepo and service layout

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

MerchantOS has a TypeScript UI, a Python API, Python workers, shared domain types, and Terraform. We need one reviewable repo without a distributed-systems zoo.

## Decision

One monorepo:

- `apps/api`, `apps/worker`, `apps/web`, `apps/agentbench`
- `packages/domain`, `db`, `shopify`, `mcp`, `agents`, `llm`, `observability`
- `infra/docker`, `infra/terraform`
- uv workspace for Python, pnpm workspace for the web app

API and worker are separate processes.

## Alternatives

- Polyrepo per service — too much overhead for one portfolio product
- Single FastAPI process for HTTP + agents + sync — webhook ACK and scaling suffer
- Next.js calling Shopify directly — violates token and tenant rules

## Tradeoffs

Monorepo CI is slightly more complex. Separate processes add a queue. We accept that for isolation and independent scaling.

## Consequences

Shared types live in `packages/domain` with no framework imports. Web does not start until an Overview API exists. No `utils/` dumping grounds.

## Amendment 2026-08-25

`packages/app` is added for application services (policy, approval, snapshot, metrics). This does not change the monorepo decision. See [contracts.md](../contracts.md) layer table.
