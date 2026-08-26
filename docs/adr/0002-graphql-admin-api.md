# ADR 0002 — Shopify GraphQL Admin API

- **Status:** Accepted
- **Date:** 2026-08-25
- **Checked:** Shopify Admin REST docs and GraphQL 2026-07 reference on 2026-08-25

## Context

MerchantOS must be a real Shopify app. Shopify currently documents REST Admin API as legacy and requires new public apps to use the GraphQL Admin API.

## Decision

All Shopify Admin reads and writes go through a typed GraphQL client behind `ShopifyPort`. Pin API version **2026-07** and re-validate at the OAuth implementation phase.

## Alternatives

- REST Admin API — rejected; official guidance for new public apps is GraphQL
- Mix REST and GraphQL — two clients, two error models, no benefit

## Tradeoffs

We must maintain typed GraphQL documents and handle GraphQL error shapes. We avoid investing in a deprecated surface.

## Consequences

`packages/shopify` is the only module that knows GraphQL documents, `X-Shopify-Access-Token`, and API version strings. Scopes are re-checked against https://shopify.dev/docs/api/usage/access-scopes before implementation.
