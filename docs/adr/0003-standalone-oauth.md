# ADR 0003 — Standalone dashboard OAuth

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

Shopify supports token exchange for embedded admin apps and authorization code grant for apps that run outside Admin. MerchantOS V1 screens are a standalone operating system UI (Overview, Ask, Approvals, …).

## Decision

V1 uses a standalone Next.js dashboard and the **authorization code grant**, with an **offline access token** for webhooks, sync, and action execution. Scopes are declared in `shopify.app.toml`.

Embedded App Bridge / token exchange / Sidekick is deferred (PRD FR-15, P2).

## Alternatives

- Embedded-only first — fights the PRD information architecture
- Client credentials grant — only for stores in our own org, not a merchant install
- Online tokens only — workers and webhooks would break when the staff session ends

## Tradeoffs

We implement OAuth ourselves instead of relying entirely on Shopify CLI templates. We get a demoable product UI and durable background access.

## Consequences

Session cookie is first-class. No Shopify token in the browser. Revisit embedding without changing `ShopifyPort`.
