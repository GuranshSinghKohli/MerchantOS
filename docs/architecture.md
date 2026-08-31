# MerchantOS Architecture

**Status:** Accepted for V1 planning  
**Sources:** [SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md), PRD v1.0, [contracts.md](contracts.md)  
**Last updated:** 2026-08-26 (Phase 9 human-approved product mutations)

MerchantOS is an AI-native commerce operating system for Shopify merchants. It is a real Shopify application, not a chatbot, analytics clone, or Shopify Admin replacement.

This document is the system overview. Detailed contracts live in sibling docs:

- [database.md](database.md)
- [agents.md](agents.md)
- [mcp.md](mcp.md)
- [security.md](security.md)
- [deployment.md](deployment.md)
- [evaluation.md](evaluation.md)
- [contracts.md](contracts.md)
- [architecture-remediation.md](architecture-remediation.md)
- [metrics.md](metrics.md)
- [adr/](adr/)

## 1. Current repository audit

Inspected 2026-08-25. The git remote is `https://github.com/GuranshSinghKohli/MerchantOS.git`. Branch `main` has **no commits**.

| Area | Exists | Missing |
|------|--------|---------|
| Product / design context | `.cursor/rules/*.mdc` | Application code |
| Documentation | this `docs/` tree | README (Phase 1) |
| Frontend | — | `apps/web` |
| API / worker | — | `apps/api`, `apps/worker` |
| Domain / DB / Shopify / MCP / agents | — | `packages/*` |
| Tests | — | unit, integration, e2e, AgentBench |
| Docker / Terraform / CI | — | `infra/`, `.github/workflows/` |
| Dependencies | none | justified additions only, per phase |

There is no existing application architecture to preserve. No PRD conflict.

## 2. Product loop

```
OBSERVE → UNDERSTAND → DIAGNOSE → PLAN → RECOMMEND → APPROVE → EXECUTE → MEASURE
```

AI is responsible for reasoning. Deterministic services are responsible for authorization, validation, calculation, persistence, execution, and security. An LLM must never bypass those controls.

## 3. Control-plane diagram

```
Merchant (browser)
    │
    ▼
apps/web  (Next.js)
    │  cookie session only — no Shopify tokens
    ▼
apps/api  (FastAPI, ECS)
    │
    ├── /health, /ready
    ├── /api/v1/*  (session, tenant from server)
    └── /api/v1/webhooks/shopify/{topic}  (HMAC, ACK < 1s)
            │
            ▼
         SQS
            │
            ▼
      apps/worker
            │
            ├── Sync consumer (ShopifyReader only) → Postgres
            ├── Agent consumer (AgentCapabilities: tools + LLM, no mutator)
            │       Orchestrator → specialists → MCP read/propose tools → Postgres
            │       → Strategy → Action Planner → PolicyService (no LLM)
            └── Execution consumer (ExecutionCapabilities: mutator, no LLM)
                    │  ApprovedAction.load from DB
                    ▼
              ShopifyMutator
                    │
                    ▼
              ActionResult + AuditEvent
```

Queue bodies are `{job_kind, job_id}` only. Tenant is loaded from the job row.

LLMs never receive Shopify credentials, never construct Admin API requests, and never see an execute tool.

## 4. Final repository structure

```
MerchantOS/
  apps/
    api/                 # FastAPI: HTTP, auth, webhooks, read APIs, enqueue
    worker/              # SQS consumers: sync, agent runs, action execution
    web/                 # Next.js merchant UI (starts when Overview exists)
    agentbench/          # Evaluation CLI (Phase 13)
  packages/
    domain/              # IDs, TenantContext, proposals, state machines
    app/                 # Application services (policy, approval, snapshot, metrics)
    db/                  # SQLAlchemy models, repositories, Alembic
    shopify/             # Reader + Mutator ports, OAuth, GraphQL, webhooks
    mcp/                 # Read/propose tool registry only
    agents/              # LangGraph nodes (no ApprovedAction, no mutator)
    llm/                 # LLMPort + OpenAI adapter + FakeLLM
    observability/       # Structured logs, request/trace IDs, OTel helpers
  infra/
    docker/              # api/worker images, compose for Postgres + Redis
    terraform/
      modules/
      envs/              # staging, production
  docs/
    adr/
  .github/workflows/
  shopify.app.toml       # Official Shopify app config (OAuth phase)
```

**Why this split**

- `api` and `worker` scale and fail independently. Webhooks must ACK without running sync or agents.
- `domain` has no framework imports so API, worker, and AgentBench share types.
- `app` is the only coordinator of domain + ports. Routers do not query SQL.
- `shopify` and `llm` are ports. Business logic and agents do not import SDKs.
- Feature-oriented modules inside packages. No `utils/` or `helpers/` dumping grounds.
- `web` is deferred until there is a real Overview API.

Python is an **uv** workspace. The web app is a **pnpm** workspace. See [ADR 0001](adr/0001-monorepo-and-service-layout.md).

## 5. Service boundaries

| Service | Owns | Must not own |
|---------|------|--------------|
| `apps/web` | UI, App Router pages, client polling | Shopify tokens, SQL, agent graphs |
| `apps/api` | Auth, session, webhook HMAC, request validation, enqueue, read models | LangGraph execution, Shopify mutations, long sync |
| `apps/worker` | Separate handlers: sync, agent, execution, webhook | A single capability object for all jobs |
| `packages/domain` | Entities, IDs, errors, proposal/approval types | FastAPI, SQLAlchemy, Shopify, OpenAI |
| `packages/app` | Policy, approval, snapshot, metrics, orchestration of ports | FastAPI, OpenAI SDK, Shopify SDK |
| `packages/db` | Persistence, RLS session, migrations | HTTP, LLM, Shopify HTTP |
| `packages/shopify` | OAuth, Reader, Mutator, HMAC, rate-limit/retry | Agent prompts, metric formulas |
| `packages/mcp` | Read/propose tools, per-agent allowlists | `ShopifyMutator`, execute tools |
| `packages/agents` | Graph, routing, node functions | `ApprovedAction`, mutator, credentials, SQL |
| `packages/llm` | Provider adapters | Domain writes |
| `packages/observability` | Logs, traces, redaction | Business decisions |

Dependency direction:

```
Frontend → API → Application services → Domain → Repositories / adapters
Agents → ToolPort.for_agent → MCP authz → Application services
ExecutionWorker → ApprovedAction.load → ShopifyMutator
```

See [contracts.md](contracts.md) for types that make a bypass a compile/import failure.

## 6. Shopify integration boundary

See [ADR 0002](adr/0002-graphql-admin-api.md), [ADR 0003](adr/0003-standalone-oauth.md), [ADR 0017](adr/0017-oauth-and-mandatory-webhooks.md).

Mandatory webhook topics: `app/uninstalled`, `customers/data_request`, `customers/redact`, `shop/redact`, plus scoped commerce topics for sync.

```
Application service
    → ShopifyPort (interface)
        → ShopifyAdapter
            → GraphQL Admin API (pinned version, currently 2026-07)
```

`ShopifyReader` (sync) and `ShopifyMutator` (execution worker only) are separate interfaces. Agent read tools do **not** call Shopify; they read tenant-scoped Postgres ([ADR 0005](adr/0005-read-path-postgres.md)). The adapter handles OAuth, versioning, pagination, rate limits, retries with backoff and jitter, idempotency, uninstall, and typed errors ([ADR 0017](adr/0017-oauth-and-mandatory-webhooks.md)).

V1 scopes (re-validate against official docs in the OAuth phase):

- Read: `read_products`, `read_orders`, `read_customers`, `read_inventory`, `read_locations`, `read_discounts`
- Write: `write_products` for allowlisted product metadata mutations only ([ADR 0023](adr/0023-phase9-human-approved-mutations.md))
- Out of V1: `write_orders`, `write_customers`, `read_all_orders` (60-day order window is an explicit constraint)

Offline access tokens are used for webhooks, sync, and execution. Tokens are envelope-encrypted and stored in `shopify_credentials`, never sent to the browser or the LLM.

## 7. Authentication and tenancy

1. Merchant completes Shopify OAuth (authorization code grant). Callback HMAC, one-time `state`, and shop allowlist are required ([ADR 0017](adr/0017-oauth-and-mandatory-webhooks.md)).
2. API stores an encrypted offline token and issues an HttpOnly, Secure, SameSite=Lax session cookie.
3. HTTP: `TenantContext.from_session`. Async: `TenantContext.from_job_row` after loading `job_id` ([ADR 0014](adr/0014-tenant-from-job-row.md)).
4. Tools receive that context from the runtime. Model-supplied tenant IDs, tool args, and queue bodies cannot construct `TenantContext`.
5. Repositories require `TenantContext` and add `merchant_id` to every query.
6. PostgreSQL RLS (`SET LOCAL app.current_merchant_id`, `ENABLE` + `FORCE`) is defense in depth for a non-`BYPASSRLS` role. Compose owner is a superuser and bypasses policies ([ADR 0018](adr/0018-phase3-closeout-deferred-controls.md)).

Details: [security.md](security.md), [ADR 0009](adr/0009-server-injected-tenant-context.md).

## 8. Asynchronous work and state

Long-running work is never done on the request thread ([ADR 0010](adr/0010-sqs-async-workers.md)):

```
API → (job row + outbox, one transaction) → publisher → SQS → capability-isolated worker
```

The API returns a job or run id (`202`). Queue messages carry ids only ([ADR 0015](adr/0015-transactional-outbox-and-leases.md)).

Workflows use explicit state machines ([ADR 0013](adr/0013-proposal-vs-approval-types.md)):

- **AgentRun:** `PENDING → RUNNING → WAITING_APPROVAL | COMPLETED | FAILED | CANCELLED` (CAS + lease)
- **Approval:** created only by merchant `ApprovalService.decide` as `APPROVED` or `REJECTED`
- **Action:** `PROPOSED → APPROVED → QUEUED → EXECUTING → COMPLETED | FAILED` or `PROPOSED → BLOCKED`
- **SyncJob:** `PENDING → RUNNING → COMPLETED | FAILED`

Delivery is at-least-once. Webhooks, sync upserts, and action execution are idempotent.

## 9. API design

Public probes: `GET /health`, `GET /ready`.  
Merchant API: `/api/v1`.  
Errors: RFC 7807 `application/problem+json`.  
`merchant_id` is never taken from the client body.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | none | Liveness |
| GET | `/ready` | none | Postgres; Redis only when `REDIS_URL` is set |
| GET | `/api/v1/auth/shopify/install` | none | Start OAuth |
| GET | `/api/v1/auth/shopify/callback` | none | Finish OAuth |
| POST | `/api/v1/webhooks/shopify/{topic}` | HMAC | Ingress (incl. uninstall + GDPR) |
| GET | `/api/v1/me` | session | Actor + store |
| GET | `/api/v1/store/sync` | session | Sync status |
| POST | `/api/v1/store/sync` | session | Enqueue sync |
| GET | `/api/v1/overview` | session | Dashboard KPIs (alias of analytics overview) |
| GET | `/api/v1/analytics/overview` | session | KPIs, trends, health, opportunities |
| GET | `/api/v1/analytics/revenue` | session | Revenue + trend |
| GET | `/api/v1/analytics/orders` | session | Orders + exclusions |
| GET | `/api/v1/analytics/products` | session | Product performance page |
| GET | `/api/v1/analytics/inventory` | session | Inventory coverage |
| GET | `/api/v1/analytics/customers` | session | New / returning (no emails) |
| GET | `/api/v1/analytics/health` | session | Deterministic health indicator |
| GET | `/api/v1/analytics/opportunities` | session | Rule-based opportunities |
| POST | `/api/v1/ask` | session | Enqueue agent run |
| GET | `/api/v1/ask/{run_id}` | session | Poll run |
| GET | `/api/v1/insights` | session | Findings |
| PATCH | `/api/v1/insights/{id}` | session | Status |
| GET | `/api/v1/approvals` | session | `Action.PROPOSED` queue |
| GET | `/api/v1/approvals/{action_id}` | session | Server-authored snapshot |
| POST | `/api/v1/approvals/{action_id}/approve` | session | Creates `ApprovalRecord` |
| POST | `/api/v1/approvals/{action_id}/reject` | session | Creates rejected approval |
| GET | `/api/v1/actions` | session | History |
| GET | `/api/v1/actions/{id}` | session | Result + audit |
| GET | `/api/v1/agent-runs` | session | List |
| GET | `/api/v1/agent-runs/{id}` | session | Graph, tools, cost |
| GET | `/api/v1/settings` | session | Connection (no tokens) |

## 10. Frontend

Approved stack ([ADR 0019](adr/0019-frontend-ui-stack.md)). Do not add alternative UI, animation, chart, client-state, or CSS libraries.

| Layer | Choice |
|-------|--------|
| Core | Next.js App Router, React, TypeScript, Tailwind CSS **3.4** |
| UI | shadcn/ui (New York, copy-in), Lucide, Sonner, next-themes |
| Animation | Motion — page/layout/entrance/hover-tap only; honor `prefers-reduced-motion` |
| Data / presentation | TanStack Query (client polling only), TanStack Table v8, Recharts |
| Forms | React Hook Form + Zod |
| Utilities | date-fns, clsx, tailwind-merge, class-variance-authority |

Server Components for first paint. TanStack Query loads analytics (query keys include filter state; tenant comes from the session cookie, never the client). Light and dark via next-themes.

Design direction: premium production B2B (Shopify Admin, Linear, Vercel). Prioritize hierarchy, typography, responsive layout, accessibility, subtle motion, and polished loading/empty/error states. No dashboard screens in this ADR — Phase 4 implements routes.

Phase 9 routes: `/`, `/analytics`, `/products`, `/inventory`, `/customers`, `/insights`, `/approvals`, `/actions`, `/settings`, `/install`. Ask/agent-runs wait for later product screens.

The web app talks only to MerchantOS `/api/v1`. It never calls Shopify.

## 11. Agents and MCP

Six specialized agents plus a deterministic `PolicyService` (not an agent). They call a per-agent MCP allowlist. There is no execute tool. See [agents.md](agents.md), [mcp.md](mcp.md), [contracts.md](contracts.md).

Financial metrics (revenue, AOV, margin, inventory quantities) are computed in application code. The LLM explains them; it is not the calculator of record.

## 12. AWS

Target: Caddy on an `edge` Fargate task (public IP, no ALB, no NAT; [ADR 0024](adr/0024-cost-optimized-aws-network.md), [ADR 0025](adr/0025-portfolio-cost-envelope.md)) → API + web on localhost → private RDS PostgreSQL, SQS + DLQ, Secrets Manager, CloudWatch, ECR. Worker is a separate Fargate Spot service. No ElastiCache in AWS (Compose Redis remains for local `/ready`). Terraform per environment. No Kubernetes in V1 ([ADR 0006](adr/0006-ecs-fargate-not-kubernetes.md)). No pgvector until knowledge search is real.

## 13. Testing strategy

| Layer | What | Live Shopify / LLM |
|-------|------|--------------------|
| Unit | Domain, state machines, metric formulas, risk tables, redaction | No |
| Contract | ShopifyPort fakes, MCP schema/authz, API request models | No |
| Integration | Postgres + RLS, queue handlers, Alembic | No |
| E2E | Install → sync → ask → approve → execute against a **development store** | Shopify yes, LLM optional |
| AgentBench CI | FakeLLM + fixtures, ≥ suites as they land | No |
| AgentBench live | Versioned report | Yes, scheduled |

Tenant isolation and unapproved-execute tests are mandatory for merchant-data and action paths. PR CI never requires a paid model.

## 14. Observability

Every important operation carries `request_id`, `trace_id`, `agent_run_id`, `tool_call_id`, and/or `action_id`. Logs are structured JSON. Tokens, secrets, and unnecessary PII are redacted. Metrics: API latency, agent/tool latency, queue depth, Shopify errors, token usage, estimated cost, action success, evaluation scores.

## 15. Open questions (not silently decided)

- Demo mutation: reduce discount depth vs change a variant price (locks write scope).
- AWS account, region (default `us-east-1` if unset), and whether staging is required before first Shopify install.
- Production web hosting: **decided in Phase 10** — ECS Fargate `web` behind the same ALB.
- Shopify Partner / Dev Dashboard app not created yet.

## 16. Phase 1

**Status:** Implemented and verified 2026-08-25. Closed.

Implemented as the engineering foundation:

- uv + pnpm monorepo, `packages/domain`, `observability`, `db`, `queue`
- `apps/api` `/health` + `/ready` (optional `/ready/queue`)
- `apps/worker` idle connectivity process (no job handlers)
- `apps/web` Next.js skeleton that only reports live `/health` (requested in the Phase 1 implementation brief; not a dashboard)
- Docker Compose: Postgres 16, Redis 7, ElasticMQ (dev-only SQS)
- Alembic bootstrap `0001_phase1` with **no** commerce/control-plane tables
- GitHub Actions: lint, format, typecheck, tests

Out of Phase 1: Shopify, LangGraph, MCP, Terraform AWS, fake dashboard data.

The Next.js skeleton is a scope expansion from the original “web starts at Overview” note. It does not change service boundaries. Health and ready stay unprefixed; business routes will use `/api/v1` later.

### Verified closeout (2026-08-25)

| Check | Result |
|---|---|
| Compose | Postgres 16, Redis 7, ElasticMQ healthy |
| Alembic | `0001_phase1 (head)` |
| `GET /health` | 200 `{"status":"ok","version":"0.1.0"}` |
| `GET /ready` | 200 `postgres: true`, `redis: true` (503 when Compose is down) |
| Worker `WORKER_ONCE=1` | Exit 0, `ElasticMqDevQueue` |
| Web `/` | 200, live health (not mock commerce data) |
| pytest (`.env` / `DATABASE_URL` set) | 18 passed, 0 skipped |
| ruff / mypy | Clean (30 mypy files) |
| web lint / tsc / vitest | Clean; 2 frontend tests passed |

Integration tests fail if `DATABASE_URL` is set and Compose is down; they do not skip. Docker Desktop’s CLI may be absent from PATH — see [README](../README.md).

Non-blocking: ElasticMQ Compose healthcheck is a no-op (`true`); application probes proved connectivity. `next lint` and Starlette TestClient emit deprecation warnings.

## 17. Phase 2

**Status:** Implemented 2026-08-25. Closed. Shopify OAuth install/uninstall only.

- `packages/shopify`: standalone authorization-code grant, callback HMAC, shop-domain allowlist, AES-256-GCM token envelope, GraphQL Admin client pinned to **2026-07**
- `GET /api/v1/auth/shopify/install` and `/callback`
- `POST /api/v1/webhooks/shopify/{topic}` (`app/uninstalled` + GDPR ACK)
- `GET /api/v1/me` and `/api/v1/settings` (session cookie; no tokens)
- Tables: merchants, stores, merchant_users, sessions, shopify_credentials, oauth_states, webhook_events, audit_events
- Scopes: read-only V1 set; no write scopes until the demo mutation is locked
- `shopify.app.toml`: `embedded = false`, mandatory compliance webhooks

Out of Phase 2: product/order/customer/inventory sync, MCP, agents, LLM, mutations, Terraform.

## 18. Phase 3

**Status:** Closed 2026-08-26. Shopify data ingestion and commerce webhooks. Do not start Phase 4 from this document.

```
Shopify GraphQL Admin 2026-07
  → SyncService (session) writes sync_jobs + outbox (one transaction)
  → publisher → SQS {job_kind, job_id}
  → SyncCapabilities worker (ShopifyReader only)
  → tenant-scoped PostgreSQL upsert

Shopify webhook
  → HMAC + skew
  → persist event_id (duplicate → 200)
  → outbox job_kind=webhook
  → ACK
  → WebhookCapabilities worker upserts/deletes projection
```

Implemented:

- Commerce tables with `UNIQUE(merchant_id, shopify_gid)`, FKs, tenant indexes, RLS `ENABLE` + `FORCE`
- `POST /api/v1/store/sync` (`202`) and `GET /api/v1/store/sync`
- Initial + incremental sync (`updated_at:>'…'` official search syntax)
- Cursor pagination (`pageInfo.hasNextPage` / `endCursor`)
- GraphQL cost throttle + HTTP 429 / `THROTTLED` backoff
- Idempotent upserts; webhook `event_id` uniqueness
- Capability-isolated worker: `SyncCapabilities` / `WebhookCapabilities` (no mutator, no LLM)
- Agents/MCP/recommendations/mutations are out of scope

Official queries used (2026-07): `products`, `orders`, `customers`, `locations` (`includeInactive`), `productVariants` + `inventoryLevels.quantities(names: ["available", "on_hand"])`, plus `product` / `order` / `customer` / `location` by id for webhook refresh.

Out of Phase 3: MCP, LangGraph, LLM, recommendations, Shopify mutations.

## 19. Phase 4

**Status:** Closed 2026-08-26. Merchant data platform and dashboard. Do not start Phase 5 from this section.

```
Shopify projection (Postgres)
  → AnalyticsRepository (SQL aggregates + TenantContext)
  → AnalyticsService (deterministic AOV, growth, health, opportunities)
  → GET /api/v1/analytics/*
  → TanStack Query
  → Next.js dashboard
```

No LLM, MCP, agents, or Shopify mutations. Metric definitions: [metrics.md](metrics.md). On-read aggregation: [ADR 0020](adr/0020-analytics-on-read.md).

### Verified closeout (2026-08-26)

Phase 2 leftovers reviewed in [ADR 0018](adr/0018-phase3-closeout-deferred-controls.md): RLS FORCE + `merchantos_app` fixed; token refresh and local HTTPS deferred.

Metric definitions: [metrics.md](metrics.md). Visual system: [DESIGN.md](DESIGN.md). On-read aggregation: [ADR 0020](adr/0020-analytics-on-read.md).

| Check | Result |
|---|---|
| Alembic | `0005_phase4 (head)` |
| Compose | Postgres 16, Redis 7, ElasticMQ (unchanged from Phase 3) |
| pytest (`DATABASE_URL` + `SQS_ENDPOINT_URL`) | 86 passed, 0 skipped (re-run after visual QA) |
| ruff / mypy | Clean |
| web lint / tsc / vitest | Clean; 12 passed, 0 skipped |
| Live dashboard QA | Chromium against Compose + Phase 3 sync projection (2026-08-26) |
| LLM / MCP / agents / mutations | Not used |

### Phase 4 deferrals (not defects)

- Slice endpoints (`revenue`, `orders`, `inventory`, `customers`, `health`, `opportunities`) reuse `overview()` internally. Extra aggregates are bounded, not N+1. Revisit if latency is measured.
- Offline token refresh and local HTTPS remain deferred ([ADR 0018](adr/0018-phase3-closeout-deferred-controls.md)).
- `/actions` is navigation only until approval-gated mutations exist.
- React Hook Form, Zod, and date-fns stay locked by [ADR 0019](adr/0019-frontend-ui-stack.md) even though Phase 4 is read-only.

## 20. Phase 5

**Status:** Closed 2026-08-26. In-process MCP read-tool layer. Do not start Phase 6 from this section.

```
Future Agent
  → ToolRegistry.for_agent
  → trusted TenantContext (from_session / from_job_row)
  → permission + Pydantic schemas
  → AnalyticsService (packages/app)
  → AnalyticsRepository
  → PostgreSQL
```

No LangGraph, LLM, propose tools, Shopify mutations, or merchant approvals. Tools never accept tenant identity. Catalog and permissions: [mcp.md](mcp.md), [ADR 0021](adr/0021-mcp-read-permissions.md). Hosting: [ADR 0004](adr/0004-mcp-in-process-registry.md).

Implemented:

- Explicit `ToolRegistry` / `AgentToolPort` (`packages/mcp`)
- Nine read-only LOW-risk commerce tools backed by `AnalyticsService`
- Resource-scoped permissions; forbidden names cannot be registered
- Input limits, typed errors, redacted `tool_invoked` telemetry
- Tenant isolation and security tests

Out of Phase 5: agents, LLM, `create_recommendation` / `create_action_plan`, execute tools, HTTP MCP server.

## 21. Phase 6

**Status:** Closed 2026-08-26. LangGraph orchestrator runtime. Do not start Phase 7 from this document.

```
POST /api/v1/ask
  → AgentRun PENDING + outbox
  → SQS {job_kind=agent_run, job_id}
  → TenantContext.from_job_row
  → AgentCapabilities (LLMPort + ToolRegistry, no mutator)
  → Orchestrator graph (plan → optional get_store_overview → finalize)
  → AgentRun COMPLETED | FAILED | CANCELLED
```

No specialist agents, propose tools, Shopify mutations, or merchant approvals. LLM output is schema-validated. Tenant is never taken from the model. [agents.md](agents.md), [ADR 0008](adr/0008-llm-provider-port.md), [ADR 0012](adr/0012-capability-isolated-workers.md).

Implemented:

- `packages/llm` (`LLMPort`, `FakeLLM`, `OpenAIAdapter`)
- `packages/agents` orchestrator graph and typed `AgentState`
- `agent_runs` / `tool_calls` persistence (Alembic `0006_phase6`)
- Ask API + worker handler + lease/idempotency
- Deterministic `apps/agentbench` runtime scenario

Out of Phase 6: Analytics/Inventory/Customer/Strategy/ActionPlanner nodes, `WAITING_APPROVAL`, live-model CI.

## 22. Phase 7

**Status:** Closed 2026-08-26. Specialized commerce agents. Do not start Phase 8 from this document.

```
POST /api/v1/ask
  → AgentRun PENDING + outbox
  → SQS {job_kind=agent_run, job_id}
  → TenantContext.from_job_row
  → Orchestrator classifies
  → allowlisted specialist (analytics | inventory | customer)
  → ToolPort.for_agent(name)
  → structured AgentResult (findings + evidence ids)
  → AgentRun COMPLETED | FAILED | CANCELLED
```

Specialists reason only. They use Phase 5 read tools and the Phase 6 LangGraph runtime. No Strategy, ActionPlanner, approvals, or Shopify mutations.

Confidence is a deterministic HIGH/MEDIUM/LOW ceiling; the model may only stay or go lower. Findings without valid evidence ids are dropped.

## 23. Phase 8

**Status:** Closed 2026-08-26. Intelligence, cross-agent synthesis, and advisory recommendations.

```
POST /api/v1/intelligence/query
  → AgentRun PENDING (run_kind=intelligence) + outbox
  → SQS {job_kind=agent_run, job_id}
  → TenantContext.from_job_row
  → allowlisted specialist selection (analytics | inventory | customer)
  → Phase 7 specialists
  → evidence aggregation + contradiction detection
  → cross-agent synthesis
  → advisory recommendations
  → IntelligenceReport
  → AgentRun COMPLETED | FAILED | CANCELLED
```

The LLM may recommend. It must not approve, construct `ApprovedAction`, or call Shopify. Insights are labeled OBSERVATION / CORRELATION / INFERENCE / HYPOTHESIS. Causal language in OBSERVATION or CORRELATION is downgraded to HYPOTHESIS. Ungrounded insights and execute/approve recommendations are dropped. Confidence and priority have deterministic ceilings. Public reports omit tenant ids and graph internals.

Out of Phase 8: Strategy, ActionPlanner, merchant approvals, Shopify mutations, new MCP or LLM provider architecture.

## 24. Phase 9

**Status:** Closed 2026-08-26. Human approval, safe actions, and controlled Shopify product mutations.

```
POST /api/v1/actions
  → SnapshotService (projection, not the model)
  → PolicyService.evaluate (no LLM)
  → Action.PROPOSED | BLOCKED
Merchant POST /api/v1/actions/{id}/approve  (or /api/v1/approvals/{id}/approve)
  → ApprovalService.decide(from_session, session_bound=True)
  → Approval.APPROVED + Action.QUEUED + outbox {job_kind=action_execute, job_id}
  → SQS
  → ExecutionWorker (ExecutionCapabilities.mutator, no LLM)
  → ApprovedAction.load
  → conflict check vs live Shopify
  → typed ShopifyMutator method
  → re-read verification
  → Action.COMPLETED | FAILED | CONFLICT | EXPIRED
  → ActionResult + audit_events
```

Executable types: `update_product_title`, `update_product_description`, `update_product_tags`, `update_product_status` (`ACTIVE`|`DRAFT`). Price, discount, delete, refund, and bulk mutations are blocked and have no mutator.

The LLM may propose field values only as untrusted merchant/API input. It cannot approve, construct `ApprovedAction`, change risk, pick a tenant, or call Shopify.

Do not start Phase 11 from this document.

## 25. Phase 10

**Status:** Cost-redesigned 2026-08-29 ([ADR 0025](adr/0025-portfolio-cost-envelope.md), [aws-cost.md](aws-cost.md)). Live AWS apply remains operator-gated.

```
Route 53 A → current edge public IPv4 → Caddy :80/:443 (Let's Encrypt)
        → api :8000 and web :3000 on localhost
worker (Fargate Spot, no inbound)
        → RDS (private) + SQS + Secrets Manager
```

No ALB, no NAT, no ElastiCache, no Cloudflare. Estimate **$33–40/month** for one environment. The task IP changes on every replace; update the A record ([staging-https.md](staging-https.md)). Shopify OAuth is valid only after HTTPS on that hostname. Destroy staging with `scripts/teardown-staging.sh` when idle.

An ALB in front of Caddy is a later production option and needs a new ADR plus a cost update.

