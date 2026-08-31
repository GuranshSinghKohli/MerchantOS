# ADR 0018 — Phase 3 closeout: token refresh, RLS FORCE, local HTTPS

- **Status:** Accepted
- **Date:** 2026-08-26
- **Extends:** [0017](0017-oauth-and-mandatory-webhooks.md) (OAuth + mandatory webhooks), [0009](0009-server-injected-tenant-context.md) / [0014](0014-tenant-from-job-row.md) (tenant isolation)
- **Does not supersede** 0014 or 0017
- **Note (2026-08-31):** The ALB TLS sentence in §3 is superseded by [0025](0025-portfolio-cost-envelope.md). Staging HTTPS is Caddy on the edge task. Token refresh remains deferred.

## Context

Phase 3 verification passed. Three Phase 2 leftovers remained before closing Phase 3:

1. Offline Shopify token refresh / rotation is stored (`encrypted_refresh_token`, `token_expires_at`) but never used.
2. PostgreSQL RLS was `ENABLE`d and not `FORCE`d. The Compose application role is the table owner and a superuser (`BYPASSRLS`), so policies were a no-op.
3. A live Partner App install requires a public HTTPS origin that local Compose does not provide.

## Decision

### 1. Token refresh — deferred (not a security hole)

Official expiring offline tokens ([Access tokens](https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens), 2026-08-26): access token lifetime is 1 hour (`expires_in` 3600); refresh token lifetime is 90 days. New public apps should request `expiring=1`. Background jobs must refresh with the stored `refresh_token` against `POST https://{shop}/admin/oauth/access_token` without merchant interaction. Existing public apps using non-expiring offline tokens must migrate by January 2027 (custom / merchant-created apps are exempt).

MerchantOS already persists the refresh ciphertext and expiry. GraphQL `401` raises `StoreUninstalledError` and the sync/webhook job fails closed. That is safe: we do not keep calling Shopify with a rejected token, and we do not invent a refresh flow.

It is an **availability** gap for a live public-app install (reads die after ~1 hour until the merchant reinstalls). There is no Partner app or production traffic yet. Implementing refresh is a real feature: official refresh request, atomic ciphertext rotation, retirement of the previous refresh token. Do not implement it in this closeout.

### 2. RLS FORCE + non-bypass app role — fixed

Verified on Compose Postgres 16: role `merchantos` is `rolsuper` and `rolbypassrls`; it owns every tenant table; `relrowsecurity` was true and `relforcerowsecurity` was false. Superusers bypass RLS even with `FORCE`. Isolation therefore lived only in repository `merchant_id` filters (which remain mandatory).

Alembic `0004_rls_force`:

- `FORCE ROW LEVEL SECURITY` on every tenant table.
- Privileged tables (`stores`, credentials, sessions, webhooks, audit, `sync_jobs`, `outbox_messages`) allow all rows when `app.current_merchant_id` is unset, otherwise restrict. Shop-domain lookup, `get_sync_job(job_id)`, and unpublished outbox must work before `TenantContext` exists.
- Commerce tables (`products`, variants, orders, …, `idempotency_keys`) match the GUC only — unset GUC returns zero rows (fail closed).
- Create login role `merchantos_app` (`NOSUPERUSER`, `NOBYPASSRLS`) and grant DML. Migrations and test `TRUNCATE` stay on the owner URL.

Local `DATABASE_URL` remains the Compose owner (`merchantos`) so Alembic can DDL. Staging/production **must** point api/worker at a non-superuser, non-`BYPASSRLS` role (create it with a Secrets Manager password *before* migrate so this revision does not create a well-known password in production). Dedicated least-privilege split (migrator vs app) in Terraform is still later.

### 3. Live HTTPS / Partner App install — deferred (ops)

Shopify requires HTTPS for the OAuth callback and webhooks ([ADR 0017](0017-oauth-and-mandatory-webhooks.md), [deployment.md](../deployment.md)). Compose serves HTTP on localhost. That is not a code defect and is not a production blocker: ALB terminates TLS in staging/production. A laptop tunnel (ngrok or Cloudflare Tunnel) is required only when installing a development store against this machine. Do not add a tunnel to Compose.

## Alternatives

- Implement refresh now — rejected until a Partner app exists; fail-closed is sufficient
- Demote Compose `POSTGRES_USER` — the official image creates a superuser; we add `merchantos_app` instead
- `FORCE` with match-only on every table — would break OAuth, uninstall, webhooks, and job-id load
- Leave ENABLE-without-FORCE — rejected; table-owner bypass is a real hole if production uses a non-superuser owner as the app role

## Tradeoffs

Privileged unset-GUC policies mean a forgotten `tenant_scope` on shop/job lookup still sees every tenant. Repositories and `TenantContext` remain the primary control. Commerce queries without a GUC now see nothing.

The Alembic-created `merchantos_app` password matches Compose (`merchantos`) and is **dev/CI only**.

## Consequences

`docs/security.md`, `docs/database.md`, `docs/architecture.md`, `docs/deployment.md`. Tests: owner role is documented as superuser; `merchantos_app` with `tenant_scope` cannot read another merchant's `products` even with a raw `SELECT`.
