# ADR 0017 — OAuth hardening and mandatory webhooks

- **Status:** Accepted
- **Date:** 2026-08-25
- **Extends:** [0003](0003-standalone-oauth.md) (standalone authorization code grant + offline token is unchanged)
- **Does not supersede 0003**

## Context

Review H8, H9: callback HMAC, uninstall, token revoke, GDPR topics, and local HTTPS for Shopify callbacks were unspecified.

## Decision

OAuth:

1. Validate Shopify `hmac` on the callback query string before exchanging the code.
2. `state` is one-time, unguessable, bound to `shop_domain`, consumed on use.
3. Shop must match `*.myshopify.com` and the state row.
4. Redirect URI is an allowlist (env), not taken from the query.
5. Offline token is envelope-encrypted; previous token is rotated on reinstall.
6. `app/uninstalled`: revoke sessions, mark store uninstalled, destroy decryptability of the token (re-encrypt-to-tombstone or delete ciphertext).

Mandatory webhook topics (V1):

- `app/uninstalled`
- `customers/data_request`
- `customers/redact`
- `shop/redact`
- Commerce topics as needed for sync: products, orders, customers, inventory (registered only for granted scopes)

Verify `X-Shopify-Hmac-Sha256`, reject skew > 5 minutes, persist `event_id` uniquely, ACK then process via outbox.

`dev`: public HTTPS tunnel (ngrok or Cloudflare Tunnel) documented for OAuth/webhooks. Not required for Phase 1 health.

## Alternatives

- Skip GDPR topics until production — fails Shopify app requirements
- Online tokens only — already rejected in 0003

## Tradeoffs

More webhook handlers. Required for a real Shopify app.

## Consequences

`docs/security.md`, `docs/architecture.md`. Tests: bad HMAC 401; uninstall makes subsequent ShopifyPort calls fail closed; replay no-op.
