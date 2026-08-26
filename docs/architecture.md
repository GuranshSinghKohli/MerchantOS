# MerchantOS Architecture

**Status:** Accepted for V1 planning  
**Sources:** [SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md), PRD v1.0, [contracts.md](contracts.md)  
**Last updated:** 2026-08-25 (Phase 1 verified)

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
- Write: exactly one of `write_discounts` or `write_products`, chosen when the demo mutation is locked
- Out of V1: `write_orders`, `write_customers`, `read_all_orders` (60-day order window is an explicit constraint)

Offline access tokens are used for webhooks, sync, and execution. Tokens are envelope-encrypted and stored in `shopify_credentials`, never sent to the browser or the LLM.

## 7. Authentication and tenancy

1. Merchant completes Shopify OAuth (authorization code grant). Callback HMAC, one-time `state`, and shop allowlist are required ([ADR 0017](adr/0017-oauth-and-mandatory-webhooks.md)).
2. API stores an encrypted offline token and issues an HttpOnly, Secure, SameSite=Lax session cookie.
3. HTTP: `TenantContext.from_session`. Async: `TenantContext.from_job_row` after loading `job_id` ([ADR 0014](adr/0014-tenant-from-job-row.md)).
4. Tools receive that context from the runtime. Model-supplied tenant IDs, tool args, and queue bodies cannot construct `TenantContext`.
5. Repositories require `TenantContext` and add `merchant_id` to every query.
6. PostgreSQL RLS (`SET LOCAL app.current_merchant_id`) is defense in depth.

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
| GET | `/ready` | none | Postgres + Redis |
| GET | `/api/v1/auth/shopify/install` | none | Start OAuth |
| GET | `/api/v1/auth/shopify/callback` | none | Finish OAuth |
| POST | `/api/v1/webhooks/shopify/{topic}` | HMAC | Ingress (incl. uninstall + GDPR) |
| GET | `/api/v1/me` | session | Actor + store |
| GET | `/api/v1/store/sync` | session | Sync status |
| POST | `/api/v1/store/sync` | session | Enqueue sync |
| GET | `/api/v1/overview` | session | Health + KPIs |
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

Next.js App Router, TypeScript, Tailwind. Server Components for first paint. TanStack Query (or equivalent) only when polling runs.

Routes: `/`, `/ask`, `/ask/[runId]`, `/insights`, `/approvals`, `/approvals/[id]`, `/actions`, `/runs`, `/settings`.

The web app talks only to MerchantOS `/api/v1`.

## 11. Agents and MCP

Six specialized agents plus a deterministic `PolicyService` (not an agent). They call a per-agent MCP allowlist. There is no execute tool. See [agents.md](agents.md), [mcp.md](mcp.md), [contracts.md](contracts.md).

Financial metrics (revenue, AOV, margin, inventory quantities) are computed in application code. The LLM explains them; it is not the calculator of record.

## 12. AWS

Target: ALB → ECS Fargate (api + worker) in private subnets with **NAT egress** to Shopify and the LLM provider → RDS PostgreSQL, ElastiCache Redis, SQS + DLQ, S3, Secrets Manager, CloudWatch, OpenTelemetry, ACM, ECR. Terraform per environment (`dev` Compose with Postgres, Redis, and ElasticMQ before the first async feature; `staging`, `production`). No Kubernetes in V1 ([ADR 0006](adr/0006-ecs-fargate-not-kubernetes.md)). No pgvector until knowledge search is real.

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
- Production web hosting: ECS with the API (default) vs a separate frontend host.
- Shopify Partner / Dev Dashboard app not created yet.

## 16. Phase 1

**Status:** Implemented and verified 2026-08-25. Closed. Do not start Phase 2 from this document.

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
