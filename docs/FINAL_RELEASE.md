# MerchantOS v1.0 — Final release

**Date:** 2026-08-31  
**Status:** Portfolio-ready prototype. Production AWS apply remains operator-gated.  
**Demo:** [demo.md](demo.md) · **Changelog:** [../CHANGELOG.md](../CHANGELOG.md)

## Product overview

MerchantOS is an AI-native commerce OS for Shopify merchants. It installs as a real standalone Shopify app, projects store data into tenant-scoped Postgres, answers business questions with evidence, and will only mutate Shopify after an authenticated merchant approves a typed action.

The invariant never changed: **LLM reasons. Deterministic services authorize, persist, and execute.**

## Architecture

```
Merchant → Next.js → FastAPI → LangGraph → MCP read tools → services → PostgreSQL
                                         ↘ Shopify Admin GraphQL (reads)
Recommendation → ActionProposal → merchant approval → ApprovedAction
  → SQS {job_kind, job_id} → worker → typed ShopifyMutator → verify → audit
Internet → HTTPS (Caddy) → ECS edge → private RDS + SQS + Secrets Manager
```

No execute MCP tool. No pgvector. No Kubernetes. No ALB. No NAT.

## Major capabilities

- Shopify OAuth, HMAC webhooks, encrypted offline tokens
- Catalog/order projection and on-read analytics
- Ask MerchantOS (intelligence graph + specialists)
- Human-approved product title / description / tags / status updates
- AgentBench FakeLLM evaluation and Phase 11 adversarial tests
- Staging AWS at ~$33–40/month ([aws-cost.md](aws-cost.md))

## Agent architecture

Orchestrator, Analytics, Inventory, Customer, Intelligence synthesis. Strategy and Action Planner are specified and not registered. Graphs are DAGs. Limits: 8s LLM timeout, 2 schema retries, 5 specialist tools, 3 specialists, 3 job attempts.

## MCP architecture

In-process allowlisted read tools. Tenant stripped from arguments. No SQL, HTTP, shell, or Shopify execute tool.

## Safety model

| Step | Owner |
|------|--------|
| Analysis / recommendation | LLM + read tools |
| Approval | Merchant session only |
| Execution | Worker + `ApprovedAction.load` + typed mutator |

The model cannot construct `ApprovedAction`, change risk, pick a tenant, or call Shopify.

## AWS deployment

Staging: DuckDNS → current edge public IPv4 → Caddy :80/:443 → API + web. Worker on Fargate Spot, no inbound. RDS private. Production Terraform is not applied automatically.

## Test results (this machine, 2026-08-31)

| Suite | Result |
|-------|--------|
| pytest | **240 passed, 0 failed, 0 skipped** |
| Vitest | **19 passed** |
| ruff | pass |
| mypy | pass (124 source files) |
| Next lint | pass |
| `tsc --noEmit` | pass |
| AgentBench CLI | **52 / 52 PASS** |
| `scripts/smoke.sh https://merchantos.duckdns.org` | **smoke ok** |
| Staging `GET /health` | `{"status":"ok"}` |
| Staging `GET /ready` | `postgres: true`, Redis skipped (ADR 0025) |

## AgentBench results

Recorded FakeLLM baseline ([evaluation.md](evaluation.md), `artifacts/eval/baseline.json`):

- Task success 1.0 · agent/tool/grounding 1.0 · hallucination 0.0
- Prompt-injection 25/25 · tenant-isolation failures 0 · unauthorized mutations 0
- Estimated CI cost $0 (no paid model)

## Security results

Phase 11 adversarial suites remain green. Emails redacted from LLM context. Tenant fields stripped from tool logs. `pnpm audit` and `pip-audit` of api/worker runtime reported no known vulnerabilities at Phase 11 close. Trivy stays report-only for official Caddy/Next **image** CVEs.

## Performance

No new N+1 or unbounded list path was introduced. Ask polls only while a run is PENDING/RUNNING. Product lists stay limit/offset. FakeLLM suite wall time on this machine: p50 5 ms, max ~38 ms (not a production SLO).

## Cost estimate

**$33–40/month** for one always-on environment (us-east-1, ADR 0025).

## Known limitations

- V1 writes: product title, description, tags, status only
- Token refresh not implemented; 401 fails closed
- Live-model quality is not a CI gate
- Production AWS is operator-gated
- Staging development stores may have **no paid orders**. The UI hides zero KPIs until import and says so. That is not a fabricated dashboard.
- Phase 12 Ask / empty-store / install polish is in this repository. Staging still serves the previously deployed web image until the next operator deploy.

## Future roadmap

Not started, not Phase 13: token refresh, additional mutation types (new ADR), live-model eval lane, optional ALB if cost allows.

## Demo

See [demo.md](demo.md). Prefer the empty-store fallback on staging unless commerce import has completed.

## Quality gate (Phase 12)

| # | Gate | Result |
|---|------|--------|
| 1 | End-to-end staging | HTTPS, `/health`, `/ready`, `/install`, OAuth start verified live. Commerce import may be empty (documented). Ask / empty-store / install polish is in this repo; staging serves the last deployed web image until the next operator deploy. |
| 2–5 | Dashboard polish, mobile, desktop, a11y | Merchant copy, focusable controls, `useReducedMotion`, semantic tables, 401 → Install. |
| 6–8 | Loading / empty / error | LoadingBoard, EmptyStoreBoard, ErrorBoard. No fake zeros when `sync_status` is `not_started`. |
| 9–12 | Intelligence / evidence / recommendations / approval | Ask MerchantOS + Approvals current vs proposed + Approve Change. |
| 13–17 | Safety | LLM cannot approve or mutate. Tenant, injection, and mutation tests remain green. |
| 18 | Performance | No new N+1; Ask polls only while running. |
| 19–22 | Docs | README, architecture §27, ADR 0027, demo.md. |
| 23–25 | Changelog / hygiene | CHANGELOG 1.0.0. No secrets in the working tree. `.env` and `terraform.tfvars` stay gitignored. |
| 26–29 | Regression | pytest 240/0/0, Vitest after Phase 12 UI, AgentBench 52/52, smoke ok. |
| 30 | Severity | No CRITICAL/HIGH product defects found in this pass. Official image CVEs remain Trivy report-only. |

## Final review (three readers)

**Shopify Staff Engineer.** The split is credible: Next.js + FastAPI + LangGraph + in-process MCP + approval-gated worker. No execute tool, no pgvector, no Kubernetes theater. Cost envelope (no ALB/NAT) is documented as a tradeoff, not hidden. The Ask screen sits on existing intelligence APIs instead of a second graph.

**Security Engineer.** Tenant still comes from session/job row only. Approval is a merchant session. The worker loads `ApprovedAction`; the model cannot construct it. Emails are redacted from LLM context. Staging does not weaken OAuth for the demo. Residual risks: token refresh is not implemented (fails closed); production apply is gated so this environment is not a production threat model.

**Hiring Manager.** The repo shows a full loop a recruiter can follow in ten minutes: install → dashboard → ask → evidence → approve → worker → audit. Evaluation is FakeLLM and honest about it. Empty-store UX is a product decision, not a missing feature.

## Resume-ready highlights

- Built an AI commerce OS where the model cannot approve or mutate Shopify
- Tenant isolation from cookie → `TenantContext` → RLS → MCP → workers
- Approval-gated typed mutations with lease recovery and idempotent SQS
- Deterministic AgentBench (52 scenarios) plus adversarial injection/isolation tests
- Cost-constrained AWS (no ALB/NAT/Redis) with HTTPS and GitHub OIDC deploy
- Merchant UX that refuses to display empty zeros as real business activity

There is no Phase 13. MerchantOS V1 stops here.
