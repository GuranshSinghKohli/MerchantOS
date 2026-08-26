# MerchantOS Database Design

**Status:** Accepted for V1 planning  
**Engine:** PostgreSQL 16 (local Compose, RDS in staging/production)  
**Migrations:** Alembic, forward-only in production  
**Related:** [ADR 0005](adr/0005-read-path-postgres.md), [ADR 0013](adr/0013-proposal-vs-approval-types.md), [ADR 0014](adr/0014-tenant-from-job-row.md), [ADR 0015](adr/0015-transactional-outbox-and-leases.md)

PostgreSQL is the source of truth for normalized application state. Shopify is the system of record for the merchant's store; MerchantOS stores a tenant-scoped projection plus control-plane state (runs, recommendations, approvals, actions, audit, evaluations).

## Conventions

| Topic | Rule |
|-------|------|
| Primary key | `id UUID` (UUIDv7) |
| Tenant | `merchant_id UUID NOT NULL` on every merchant-owned table |
| Store | `store_id UUID NOT NULL` where the row belongs to one shop |
| Shopify identity | `shopify_gid TEXT` (e.g. `gid://shopify/Product/123`) |
| Timestamps | `created_at`, `updated_at` timestamptz |
| Soft delete | `deleted_at` only where Shopify can delete the resource |
| JSONB | Agent metadata, tool I/O redacted copies, evidence, eval expect — not core entities |
| Isolation | Repositories require `TenantContext`; RLS `SET LOCAL app.current_merchant_id` (`ENABLE` + `FORCE`; see [ADR 0018](adr/0018-phase3-closeout-deferred-controls.md)) |
| Money / counts | `NUMERIC` / `INTEGER` computed in application code, stored as facts |

Do not hide business rules in SQL. Do not query merchant data without a tenant. Do not join `shopify_credentials` into list queries.

## ERD (logical)

```
merchants 1──* stores
stores 1──1 shopify_credentials
stores 1──* products 1──* variants
stores 1──* locations
stores 1──* customers
stores 1──* orders 1──* order_lines → variants
variants *──* inventory_snapshots → locations

merchants 1──* merchant_users 1──* sessions
merchants 1──* agent_runs 1──* agent_messages
agent_runs 1──* tool_calls
agent_runs 1──* recommendations
agent_runs 1──* actions 1──0..1 approvals
actions 1──* action_results
merchants 1──* audit_events
merchants 1──* outbox_messages
stores 1──* webhook_events
stores 1──* sync_jobs
merchants 1──* idempotency_keys
stores 1──* metrics
stores 1──* insights

evaluation_scenarios 1──* evaluation_metrics ← evaluation_runs
```

Evaluation catalog tables are global (not tenant-scoped). All other merchant data is tenant-scoped.

## Identity

### merchants

Purpose: MerchantOS tenant.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| name | TEXT | |
| status | TEXT | `active` \| `suspended` |
| created_at, updated_at | timestamptz | |

### stores

Purpose: one Shopify shop (V1: one store per merchant).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| merchant_id | UUID FK → merchants | tenant |
| shop_domain | TEXT UNIQUE | |
| myshopify_domain | TEXT UNIQUE | |
| shopify_shop_gid | TEXT | |
| currency | CHAR(3) | |
| iana_timezone | TEXT | |
| plan_name | TEXT | |
| installed_at | timestamptz | |
| uninstalled_at | timestamptz | nullable |
| sync_status | TEXT | state machine |
| sync_error | TEXT | redacted |
| last_synced_at | timestamptz | |

Indexes: `merchant_id`, `myshopify_domain`.

### merchant_users

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| merchant_id | UUID FK | |
| email | TEXT | |
| role | TEXT | `owner` \| `member` |

UNIQUE(`merchant_id`, `email`).

### sessions

Server-side session. Cookie stores only the session id.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| merchant_id | UUID FK | |
| user_id | UUID FK → merchant_users | |
| store_id | UUID FK → stores | |
| expires_at | timestamptz | |
| revoked_at | timestamptz | nullable |

Index: `expires_at`.

### shopify_credentials

Isolated table. Selected only by the Shopify adapter.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| merchant_id | UUID FK | |
| store_id | UUID FK UNIQUE | |
| encrypted_offline_token | BYTEA | envelope encrypted |
| encrypted_refresh_token | BYTEA | nullable; required for expiring offline tokens |
| token_expires_at | timestamptz | from `expires_in` |
| refresh_token_expires_at | timestamptz | nullable |
| scopes | TEXT[] | granted scopes |
| key_version | TEXT | Secrets Manager / local key id |

### oauth_states

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| state | TEXT UNIQUE | |
| shop_domain | TEXT | |
| expires_at | timestamptz | |
| consumed_at | timestamptz | nullable |

## Commerce projection

UNIQUE(`merchant_id`, `shopify_gid`) on every Shopify-backed entity.

### products

`title`, `status`, `vendor`, `product_type`, `tags TEXT[]`, `published_at`, `deleted_at`.  
Index: GIN(`tags`).

### variants

`product_id` FK, `sku`, `title`, `price NUMERIC(12,2)`, `compare_at_price`, `cost NUMERIC(12,2)` nullable, `inventory_item_gid`.

### locations

`name`, `active`. Required for inventory.

### customers

`email`, `orders_count`, `total_spent`, `state`, `first_order_at`, `last_order_at`, `deleted_at`.  
Index: `(merchant_id, last_order_at)`.  
PII minimized; do not store payment methods.

### orders

`customer_id` nullable FK, `name`, `processed_at`, `financial_status`, `fulfillment_status`, `subtotal`, `total_discounts`, `total_price`, `currency`, `cancelled_at`.  
Index: `(merchant_id, processed_at DESC)`.

### order_lines

`order_id` FK, `variant_id` FK nullable, `quantity`, `price`, `discount_allocation`, `cost_at_sale` nullable.

### inventory_snapshots

`variant_id`, `location_id`, `available`, `on_hand`, `captured_at`.  
UNIQUE(`merchant_id`, `variant_id`, `location_id`, `captured_at`).  
Index: `(merchant_id, captured_at DESC)`.

## Derived

### metrics

Deterministic facts written by application jobs, not by the LLM.

UNIQUE(`merchant_id`, `name`, `grain`, `period_start`, `dimensions`)  
`grain`: `day` \| `week` \| `month`. `value NUMERIC`. `dimensions JSONB`.

### insights

Proactive findings: `severity`, `confidence`, `title`, `body`, `evidence JSONB`, `status` (`open` \| `ack` \| `resolved`), `agent_run_id` nullable.

## Control plane

### agent_runs

Implemented in Alembic `0006_phase6`. Phase 7 stores the specialist name in `classification` and structured `AgentResult` fields in `result_json`. `WAITING_APPROVAL` remains unused.

| Column | Notes |
|--------|-------|
| question | merchant text (untrusted) |
| status | `PENDING` \| `RUNNING` \| `WAITING_APPROVAL` \| `COMPLETED` \| `FAILED` \| `CANCELLED` |
| lease_owner, lease_until | single-flight; reaper after expiry |
| classification, plan | JSONB |
| started_at, finished_at, latency_ms | |
| token_input, token_output, estimated_cost_usd | |
| error_code, error_message | no stack traces to clients |

Index: `(merchant_id, created_at DESC)`.

### agent_messages

`run_id` FK, `agent`, `role`, `payload JSONB`. No secrets in payloads.

### tool_calls

`tool_name`, `risk_level`, `permission`, `input_redacted`, `output_redacted`, `status`, `latency_ms`, `error_code`.

### recommendations

PRD fields: `problem`, `evidence`, `hypothesis`, `proposed_action`, `expected_impact`, `confidence`, `risks`, `affected_resources`, `measurement_plan`, `status`.  
**Do not store `approval_required`.** PolicyService decides whether an `Action` is created.

### actions

State: `PROPOSED` \| `APPROVED` \| `QUEUED` \| `EXECUTING` \| `COMPLETED` \| `FAILED` \| `BLOCKED`.  
`type` is an allowlisted enum. `payload`, `payload_hash`, `before_state`, `after_state` are written by `SnapshotService` at `PROPOSED` and are immutable (trigger).  
`lease_owner`, `lease_until` for `EXECUTING`.  
UNIQUE(`merchant_id`, `idempotency_key`).  
Agents insert `PROPOSED` or `BLOCKED` only via `create_action_plan` → application service. They cannot set `APPROVED`.

### approvals

Created **only** by `ApprovalService.decide` from a merchant session.  
State at insert: `APPROVED` \| `REJECTED`. (No agent-created `PENDING` row. The queue is `actions.status = PROPOSED`.)  
Columns: `action_id` UNIQUE, `frozen_payload_hash` (must match `actions.payload_hash`), `risk_level`, `permissions`, `decision_reason`, `expires_at` (for unused approvals if we expire PROPOSED actions instead), `decided_by`, `decided_at`.  
INSERT from the approval API role/service only. Agents have no write path.

### action_results

`ok`, `shopify_request_id`, `mutation_name`, `error_code`, `response_redacted`.

Creating merchant approval and transitioning `Action` to `APPROVED` is one transaction, plus an outbox row for the execution queue. Execution result and audit row are written together; Shopify success + DB failure retries on `action_id`.

### audit_events

`actor_type` (`user` \| `system` \| `agent` \| `webhook`), `actor_id`, `request_id`, `run_id`, `event_type`, `resource_type`, `resource_id`, `metadata JSONB` (pre-redacted).  
Indexes: `(merchant_id, created_at DESC)`, `(request_id)`.

## Jobs

### outbox_messages

Written in the same transaction as the job row. Publisher relays to SQS.

| Column | Notes |
|--------|-------|
| id | UUID PK |
| merchant_id | FK, from the job row (not from the queue later) |
| job_kind | `agent_run` \| `sync` \| `webhook` \| `action_execute` |
| job_id | UUID of the corresponding row |
| created_at | |
| published_at | nullable until relayed |

Index: `(published_at) WHERE published_at IS NULL`.

### webhook_events

`topic`, `shop_domain`, `event_id UNIQUE`, `payload_hash`, `resource_gid`, `payload_json` (resource identifiers only — not full customer records), `status`, `received_at`.  
`merchant_id` / `store_id` set by looking up `shop_domain` **before** enqueue. Unknown shop (valid HMAC, unknown install) is stored with null tenant, not processed, alerted. After lookup, RLS applies.  
Duplicate `event_id` → 200 no-op. Commerce topics write `outbox_messages` in the same transaction; the HTTP handler does not upsert the catalog.

### sync_jobs

`kind` (`initial` \| `incremental`), `resource`, `status`, `cursor`, `attempt`, `lease_owner`, `lease_until`, UNIQUE(`merchant_id`, `idempotency_key`).

### idempotency_keys

UNIQUE(`merchant_id`, `scope`, `key`). Stores a response hash and expiry.

## Evaluation (global)

### evaluation_scenarios

`slug UNIQUE`, `suite`, `version`, `fixture_ref`, `expect JSONB`.

### evaluation_runs

`git_sha`, `model`, `prompt_version`, `graph_version`, `tool_version`, timestamps.

### evaluation_metrics

Per scenario: `task_success`, `tool_accuracy`, `groundedness`, `action_accuracy`, `safety_violations`, `latency_ms`, `cost_usd`.

## Migration strategy

1. Phase 2: identity, sessions, audit, RLS, `oauth_states`, `shopify_credentials` (OAuth/uninstall cannot wait). Expiring offline tokens also store `encrypted_refresh_token` (official requirement for new public apps). Refresh/rotation of that token is deferred ([ADR 0018](adr/0018-phase3-closeout-deferred-controls.md)).
2. Phase 3: commerce projection (products, variants, locations, customers, orders, order_lines, inventory_snapshots) plus `sync_jobs`, `outbox_messages`, and `idempotency_keys`. Ingestion cannot persist without these tables. `webhook_events` also stores `resource_gid` and identifier-only `payload_json` so workers can apply deletes/inventory without keeping customer PII on the request thread.
3. Phase 3 closeout: `FORCE ROW LEVEL SECURITY` and DML role `merchantos_app` (`NOSUPERUSER`, `NOBYPASSRLS`). Compose owner `merchantos` remains a superuser for Alembic.
4. Later phases: metrics, insights, agent/control, eval. Terraform must create the production app role with a Secrets Manager password before migrate.

This supersedes the earlier planning note that deferred commerce tables to Phase 5 — that contradicted `SYSTEM_DESIGN.md` Phase 3 (Shopify data ingestion).

Alembic versions are the only schema source of truth. No manual production DDL.

## Index and constraint checklist

- Tenant column + FK on every merchant-owned table
- `(merchant_id, shopify_gid)` unique for Shopify resources
- Time-range list indexes for orders, runs, audit
- Phase 4: `(merchant_id, store_id, processed_at)` on orders; `(merchant_id, first_order_at)` on customers; `(merchant_id, order_id)` on order_lines
- Action idempotency unique
- Webhook `event_id` unique
- Credentials table not referenced by ORM relationships used in list endpoints
