# MerchantOS final verification audit

**Date:** 2026-08-31  
**Auditor:** independent pass over the working tree + live staging. Prior phase closeouts were not trusted.  
**HEAD on origin:** `31dc703` (`main`)  
**Working tree:** Phases 11–12 uncommitted (Ask UI, AgentBench corpus, docs).  
**Production Terraform:** not applied.

## Release decision

# READY FOR FINAL RELEASE

## Exact results (this machine, this pass)

| Suite | Result |
|-------|--------|
| pytest | **240 passed, 0 failed, 0 skipped** (`uv run pytest`, Compose Postgres/Redis/ElasticMQ up) |
| Vitest | **19 passed** (8 files) |
| ruff check | pass |
| ruff format | pass after one newline fix in `apps/agentbench/src/merchantos_agentbench/scenarios.py` |
| mypy | pass (124 source files) |
| Next lint | pass |
| `tsc --noEmit` | pass |
| `next build` | pass (14 routes; `/ask` in the **local** bundle) |
| AgentBench CLI | **52 passed, 0 failed** (`artifacts/eval/latest.json`, FakeLLM, cost `$0`) |
| Local `GET /health` | 200 `{"status":"ok","version":"0.1.0"}` |
| Local `GET /ready` | 200 `postgres: true`, `redis: true` |
| Local `GET /ready/queue` | 200 `{"queue":true}` |
| Worker `WORKER_ONCE=true` | started twice against ElasticMQ (empty queue; restart recovered) |
| Staging smoke | **`smoke ok https://merchantos.duckdns.org`** |
| Staging `GET /health` | 200, `via: 1.1 Caddy`, HTTP/2 |
| Staging `GET /ready` | 200 `postgres: true`, `redis: skipped` (ADR 0025) |
| GitHub CI (`ci.yml` on `31dc703`) | **success** |
| GitHub deploy (`deploy.yml` on `31dc703`) | images + migrate + ECS update succeeded; **smoke step failed** (DuckDNS lag after edge IP replace). Live smoke now passes. |

AgentBench rates (recorded, not invented): task/agent/tool/grounding/structure 1.0; hallucination 0.0; prompt-injection 25/25; tenant-isolation failures 0; unauthorized mutations 0.

## Quality table

| Category | Result | Evidence |
|----------|--------|----------|
| Repository | PASS | Monorepo matches `docs/architecture.md` §4. No TODO/FIXME in source. `SYSTEM_DESIGN.md` is the product spec (no separate `PRD` file). |
| Local environment | PASS | Compose Postgres, Redis, ElasticMQ healthy. Alembic `upgrade head` applied. `.env` is gitignored. |
| Docker | PASS | `infra/docker/compose.yml` is local deps only. API/worker/web/Caddy Dockerfiles exist; CI/deploy build them. |
| Database | PASS | pytest DB/RLS/migrate suites green. Local `/ready` postgres true. Staging `/ready` postgres true. |
| Queue | PASS | Local `/ready/queue` true (ElasticMQ). Staging uses SQS; queue is not on `/ready` (ADR 0025). Worker pings the queue on start. |
| API | PASS | Local + staging health/ready. Unauthenticated `/api/v1/me`, analytics, and `POST /actions` return 401 on staging. |
| Frontend | PASS | Vitest 19, lint, tsc, production build. Ask / empty-store / install polish exist in the **working tree**. Staging web image is still `31dc703` (no `/ask`). Browser visual QA was not run (no browser tools). |
| Shopify OAuth | PASS | Staging `GET /install` 200. Invalid shop → 400. Valid shop → 302 to Shopify authorize with HTTPS callback `https://merchantos.duckdns.org/api/v1/auth/shopify/callback` and a `state` param. Cookie is httponly / SameSite=lax / `secure` when `app_env != dev`. Live merchant callback was not re-clicked this session; `apps/api/tests/test_oauth.py` covers it. |
| Commerce sync | NOT APPLICABLE | Worker sync/pagination/idempotency tests pass. Staging store is not shown as imported commerce data this pass. No KPI numbers were assumed. |
| Agents | PASS | AgentBench 52/52 + `packages/agents/tests`. Graphs are DAGs (`test_phase11_bounds.py`). Limits: 8s LLM, 2 schema retries, 5 specialist tools, 3 intel agents, 40s graph timeout. |
| MCP | PASS | In-process allowlist only. Forbidden names include `execute_sql`, `http_request`, `run_shell`, `raw_shopify_graphql`, `execute_approved_action`. Isolation test asserts tenant B revenue `999.00` / `Product b1` / `beta.myshopify.com` are absent when invoked as tenant A. |
| AgentBench | PASS | 52/52 FakeLLM. Prompt-injection 25, tool-abuse 8, tenant-isolation 2, reliability 2. |
| Prompt injection | PASS | AgentBench injection suite + `packages/agents/tests/test_security.py` / intelligence injection tests. Commerce text is redacted (`redact_untrusted_text`). |
| Tenant isolation | PASS | Two-tenant MCP test, RLS FORCE test, action isolation API test, AgentBench `intel-cross-tenant` / `customer-tenant-switch`. |
| Action security | PASS | `ApprovedAction` has no public constructor. Approve routes require a session (`session_bound=True`). Unauthenticated approve/propose is 401. No execute MCP tool. Worker loads `ApprovedAction` only. |
| Reliability | PASS | Shopify 429 backoff tests, LLM timeout/malformed FakeLLM cases, lease recovery (`test_phase11_lease_recovery.py`), duplicate SQS/lease hold. Worker restarted twice locally. |
| AWS staging | PASS | HTTPS + Caddy + `/ready` RDS. Worker is separate (smoke does not hit it). Cost envelope still the ADR 0025 estimate **$33–40/month**. Production apply not run. |
| CI/CD | PASS | `ci.yml` green on HEAD. Deploy built/pushed/migrated. Smoke in Actions failed once because the edge public IP changed and DuckDNS was stale (`staging-https.md`). That is the no-ALB tradeoff, not a broken image pipeline. |
| Security | PASS | Secrets Manager / gitignored `.env` + `*.tfvars`. Session cookie flags. Tenant from session/job row only. LLM cannot approve. Staging unauth APIs 401. Official image CVEs remain Trivy report-only (`exit-code: 0`). |
| Performance | PASS | No new unbounded list path found. Product list is limit/offset. Agent bounds as above. Ask first-load JS ~130 kB in the local build. AgentBench wall ~0.5 s FakeLLM (not an SLO). |
| Documentation | PASS | README, architecture §27, ADRs 0026/0027, demo, CHANGELOG, FINAL_RELEASE match the **repo**. Staging Ask 404 is documented, not claimed live. ADR 0018 ALB sentence marked superseded by 0025 this pass. `docs/architecture-remediation.md` is a 2026-08-25 historical log (H11 still mentions NAT); current network is ADR 0025 (no NAT). |
| Secrets | PASS | `.env` and `*.tfvars` gitignored. Diff has test placeholders (`shpua_test`, `AWS_SECRET_ACCESS_KEY=local`) only. Shopify `client_id` on the authorize URL is the public app key. |
| Regression | PASS | Full pytest + Vitest + AgentBench + local probes + staging smoke this pass. |

## Defects found and fixed this pass

1. **CI format gate** — `ruff format --check` failed on a missing blank line in `scenarios.py`. Fixed. Format check now passes.  
2. **Isolation assertion** (already in tree) — `'999' in blob` matched a timestamp microsecond, not tenant B’s `$999.00`. Assertion now uses `999.00`, `Product b1`, `beta.myshopify.com`.  
3. **ADR 0018** — §3 still said ALB terminates TLS. Added a superseded note pointing at ADR 0025. Decision body not rewritten.

No security vulnerability required a code change.

## What was not claimed

- Live Shopify catalog/order projection on staging (empty/unimported store).  
- Live merchant OAuth callback click this session.  
- Live Shopify mutation this session.  
- Browser desktop/mobile/keyboard walkthrough.  
- Production AWS.  
- Paid-model quality.  
- GitHub deploy smoke always green after an edge replace without updating DuckDNS.

## Known non-blocking limitations

- Token refresh is deferred (ADR 0018); GraphQL 401 fails closed.  
- V1 writes: product title, description, tags, status only.  
- No ALB: update DuckDNS after every edge task replace before trusting CI smoke.  
- Phase 12 UI is in the working tree; staging `/ask` is 404 until commit + deploy.  
- Compose `merchantos` is a superuser; staging/prod must use `merchantos_app` (ADR 0018).  
- AgentBench is FakeLLM; not a `ci.yml` job (pytest harness + local CLI).

## Final git status (this pass)

Uncommitted Phase 11–12 productization + this audit. No secrets staged. `.env`, `terraform.tfvars`, and `artifacts/eval/latest.json` remain ignored.

No Phase 13.
