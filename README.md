# MerchantOS

AI-native commerce operating system for Shopify merchants.

MerchantOS is a real Shopify app: official OAuth, encrypted tokens, Admin API reads, approval-gated product writes, and a merchant dashboard. It is not a chatbot bolted onto Shopify Admin, and it is not a Shopify clone.

**The model recommends. The merchant approves. Deterministic code executes.**

**[Demo video (90s)](docs/MerchantOS-demo.mp4)** · Canonical design: [`SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md) · Architecture: [`docs/architecture.md`](docs/architecture.md) · Release: [`docs/FINAL_RELEASE.md`](docs/FINAL_RELEASE.md) · Live walkthrough: [`docs/demo.md`](docs/demo.md)

## Problem

Merchants get dashboards full of charts and chatbots that invent numbers or, worse, write to the store. MerchantOS separates reasoning from authority: LangGraph agents may read allowlisted tools and propose a change. They cannot approve it, pick a tenant, or call Shopify.

## What it does

- Connect a development store with standalone Shopify OAuth
- Import catalog and order data into a tenant-scoped projection
- Show revenue, orders, inventory, and customers from that projection
- Answer a business question with evidence, confidence, and limits
- Recommend a product change with current vs proposed state
- Require an explicit merchant approval before any mutation
- Execute a typed Shopify write, verify it, and keep an audit trail

## Architecture

```
Merchant
  → Next.js dashboard (apps/web)
  → FastAPI (apps/api)
  → LangGraph agents (packages/agents)
  → MCP-compatible read tools (packages/mcp)
  → Analytics / Policy / Approval services (packages/app)
  → PostgreSQL
  → Shopify Admin GraphQL (reads + typed mutator)
```

```
Recommendation
  → ActionProposal
  → Merchant approval (session only)
  → ApprovedAction.load
  → SQS {job_kind, job_id}
  → Worker (no LLM on the execution path)
  → ShopifyMutator
  → Re-read verification + audit
```

```
Internet → HTTPS (Caddy on ECS)
  → API :8000 + web :3000 on localhost
Worker (Fargate Spot, no inbound)
  → private RDS + SQS + Secrets Manager
```

There is **no execute MCP tool**, **no pgvector**, **no Kubernetes**, **no ALB**, **no NAT Gateway**.

## Agents and MCP

Allowlisted specialists: Analytics, Inventory, Customer, plus an Intelligence graph that synthesizes them. Strategy and Action Planner are specified and **not registered**.

Tools are an in-process registry (`ToolPort.for_agent`). Tenant identity comes from `TenantContext.from_session` / `from_job_row` only. Unknown tools, SQL, HTTP, and shell names fail closed.

## Safety

| Actor | May do | Must not do |
|-------|--------|-------------|
| LLM | Reason, call read tools, draft recommendation text | Approve, construct `ApprovedAction`, pick tenant, call Shopify |
| Merchant session | Approve or reject | Bypass policy or change risk |
| Execution worker | Typed mutator after `ApprovedAction.load` | Run the model |

Risk is assigned from `ACTION_RISK_TABLE` + affected count. CRITICAL deletes and bulk price changes are blocked.

## Stack

Next.js 15 / React 19 / Tailwind 3.4 / shadcn + Lucide + TanStack Query · FastAPI / Pydantic · LangGraph · PostgreSQL · SQS · ECS Fargate · RDS · Secrets Manager · Terraform · GitHub Actions.

## AWS and cost

Staging is live under a DuckDNS hostname (see [`docs/staging-https.md`](docs/staging-https.md)). Production Terraform apply is **operator-gated**.

Honest idle cost for one environment: **~$33–40/month** ([`docs/aws-cost.md`](docs/aws-cost.md), [ADR 0025](docs/adr/0025-portfolio-cost-envelope.md)).

## Local development

```bash
cp .env.example .env
make deps
make up
make migrate
```

```bash
make api      # http://localhost:8000/health  /ready
make worker
make web      # http://localhost:3000
```

`GET /health` does not need dependencies. `GET /ready` needs Postgres. Redis is required only when `REDIS_URL` is set.

Open `/install` and enter `{store}.myshopify.com`. Tokens never reach the browser.

## Staging

```bash
scripts/smoke.sh https://merchantos.duckdns.org
scripts/edge-public-ip.sh   # after every edge replace, update DuckDNS first
```

After OAuth, Overview shows **Connected**. If commerce sync has not run, the dashboard explains that and offers **Import store data** instead of fake zeros.

## Testing and evaluation

```bash
make lint
make typecheck
make test
uv run python -m merchantos_agentbench.runner
```

CI uses `FakeLLM`. Live-model AgentBench is operator-gated. Baseline: [`artifacts/eval/baseline.json`](artifacts/eval/baseline.json). Methodology: [`docs/evaluation.md`](docs/evaluation.md).

## Security

Tenant isolation at API, repositories, tools, and FORCE RLS. Secrets in AWS Secrets Manager / gitignored `.env`. Prompt injection is treated as untrusted merchant data. See [`docs/security.md`](docs/security.md).

## Project structure

```
apps/api          FastAPI
apps/worker       Sync, webhooks, agents, execution
apps/web          Merchant dashboard
apps/agentbench   Deterministic evaluation harness
packages/*        Domain, MCP, agents, Shopify, DB, queue
infra/terraform   Staging / production AWS
docs/             Architecture, ADRs, demo, release
```

## Design decisions

ADRs live in [`docs/adr/`](docs/adr/). Current ones that interviewers usually want: 0012 capability-isolated workers, 0013 proposal vs approval types, 0014 tenant from job row, 0021 MCP read permissions, 0023 human-approved mutations, 0025 portfolio cost envelope, 0026 eval/hardening, 0027 productization.

## Demo

**[Watch the 90-second demo](docs/MerchantOS-demo.mp4)** — Ask → evidence-backed answer → merchant approval → worker execution. Recorded against the live staging app. The store had no paid orders; the answer says so. The approved title change failed on a rejected Shopify token and stayed on the audit trail.

Operator walkthrough: [`docs/demo.md`](docs/demo.md). Do not paste invented KPI numbers. Staging may be empty until import — that empty state is honest, not a fake dashboard.

## Limitations

- V1 mutations: product title, description, tags, status (`ACTIVE`/`DRAFT`) only
- Token refresh is not implemented; GraphQL 401 fails closed
- Live-model quality is not a CI gate
- Production AWS is not auto-applied
- Empty development stores stay empty until import/sync runs — that is honest, not a demo fake

## Future (not started)

Token refresh, richer mutations after a new ADR, live-model eval lane, optional ALB if cost allows. There is no Phase 13 in this repository.

## License / use

Portfolio prototype. Development-store data only unless an operator applies production Terraform with a separate account and secrets.
