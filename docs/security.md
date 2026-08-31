# MerchantOS Security Model

**Status:** Accepted for V1 planning  
**Related:** [contracts.md](contracts.md), [ADR 0014](adr/0014-tenant-from-job-row.md), [ADR 0013](adr/0013-proposal-vs-approval-types.md), [ADR 0017](adr/0017-oauth-and-mandatory-webhooks.md), [ADR 0018](adr/0018-phase3-closeout-deferred-controls.md)

Security is designed in from Phase 1. It is not a late hardening sprint.

## Principles

- Least privilege at Shopify scopes, AWS IAM, and tool permissions
- Tenant isolation at API, service, repository, tool, and database
- LLM is untrusted
- Secrets never in git, logs, agent context, frontend, or plaintext DB
- Fail closed on authz, risk, and validator errors
- Merchant data (titles, notes, questions) is untrusted DATA

## Authentication

| Surface | Mechanism |
|---------|-----------|
| Merchant dashboard | Server-side session cookie after Shopify OAuth |
| Shopify webhooks | `X-Shopify-Hmac-Sha256` + timestamp skew window |
| ECS tasks | IAM task roles — no long-lived AWS keys in env files |
| Production secrets | AWS Secrets Manager |
| Local secrets | `.env` gitignored; `.env.example` committed empty of values |

Cookie flags: `HttpOnly`, `Secure` (non-dev), `SameSite=Lax`. Session id only. CSRF protection on cookie-authenticated POSTs.

Shopify: authorization code grant; offline token for workers. Callback **HMAC**, one-time `state`, shop allowlist, redirect URI allowlist ([ADR 0017](adr/0017-oauth-and-mandatory-webhooks.md)). Token exchange / embedded App Bridge is later.

## Authorization

- HTTP: `TenantContext.from_session`. Jobs: `TenantContext.from_job_row`. Queue bodies and LLM output cannot supply tenant.
- Foreign resource ids return **404**, not 403.
- Tool permissions are allowlists in code (`ToolPort.for_agent`).
- `ApprovalRecord` is created only by `ApprovalService.decide` (merchant session). Agents have no write path.
- Shopify mutations only via `ApprovedAction.load` in the execution worker. No execute MCP tool.

## Tenant isolation

```
Authenticated request → TenantContext.from_session
  → persist job row (merchant_id on the row) + outbox
  → SQS {job_kind, job_id}
  → TenantContext.from_job_row
  → tool/repository + RLS
```

Tests with two merchants on every list/get path are mandatory once those APIs exist.

RLS is `ENABLE` + `FORCE` on tenant tables ([ADR 0018](adr/0018-phase3-closeout-deferred-controls.md)). Commerce tables return no rows when `app.current_merchant_id` is unset. Privileged identity/job tables allow an unset GUC so shop-domain lookup and `job_id` load still work. Repositories still require `TenantContext` and add `merchant_id` in SQL.

Compose `DATABASE_URL` user `merchantos` is a superuser (`BYPASSRLS`) — policies do not apply to it. Role `merchantos_app` is `NOSUPERUSER` / `NOBYPASSRLS`. Staging and production api/worker must not connect as a superuser or `BYPASSRLS` role.

Offline access tokens: ciphertext and refresh material are stored; refresh/rotation is not implemented. GraphQL `401` fails closed (`StoreUninstalledError`). Required before a live public-app install lasts more than one hour; not a fail-open hole.

## Secrets

| Secret | Store | Consumers |
|--------|-------|-----------|
| Shopify client secret | Secrets Manager / local env | api |
| Offline access tokens | `shopify_credentials` BYTEA, envelope encrypted | shopify adapter |
| Session signing key | Secrets Manager / local env | api |
| LLM API key | Secrets Manager / local env | worker via llm adapter |
| DB credentials | Secrets Manager / compose | api, worker |

Agents never receive raw tokens. `shopify_credentials` is not joined into list queries.

Phase 2: AES-256-GCM local envelope (`TOKEN_ENCRYPTION_KEY` + `key_version`). Uninstall overwrites ciphertext with a tombstone so decrypt fails closed. `/api/v1/me` and `/settings` never include token fields. Callback HMAC, one-time shop-bound `state`, and `*.myshopify.com` validation are enforced before token exchange.

Phase 3: commerce webhooks ACK after HMAC + unique `event_id`; catalog writes happen on the worker. Webhook `payload_json` stores resource GIDs only. Sync/worker logs include `job_id`, `store_id`, `resource`, counts, and error types — never access tokens or raw customer payloads. Repositories require `TenantContext`. Agents have no import path into this layer.

Phase 4: analytics endpoints take date filters only. Tenant comes from the session cookie. Responses omit customer email, tokens, and stack traces. Two-merchant tests cover every analytics path.

Phase 5: MCP tools are an interface over the same `AnalyticsService`. Tenant identity is stripped from arguments and taken only from `TenantContext.from_session` / `from_job_row`. Permissions are resource-scoped (`analytics:read`, `products:read`, `inventory:read`, `orders:read`, `customers:read`). There is no SQL, HTTP, shell, credential, or Shopify tool. Unknown and forbidden names fail closed. Telemetry logs `tool_call_id`, tool name, tenant ids, duration, and error category — never tokens or emails.

Phase 6: the orchestrator reasons through `LLMPort`. `AgentState` has no tenant, token, or approval fields. Tool calls go through `ToolPort.for_agent("orchestrator")` (`get_store_overview` only). Invalid model output is rejected; `status: APPROVED` cannot persist an approval. Worker `AgentCapabilities` has no `ShopifyMutator`. API keys stay in process settings and never enter state, prompts, or `agent_runs` rows.

Phase 7: specialists bind `ToolPort.for_agent(analytics|inventory|customer)` from an allowlisted registry. Model output cannot load arbitrary agents. Merchant text is untrusted DATA. Findings must cite evidence ids extracted from tool output. Customer results must not include emails.

Phase 8: the intelligence graph inherits the same trusted tenant. Specialist outputs and merchant fields remain untrusted DATA. Synthesis cannot merge tenants, load arbitrary agents, approve actions, or emit `ApprovedAction`. Emails are redacted before LLM context and from the public report. Execute/approve recommendation text is dropped.

Phase 9: approval requires `TenantContext.from_session` and `session_bound=True`. `ApprovedAction` cannot be constructed from LLM output. Execution uses `ExecutionCapabilities` (mutator, no LLM) and typed `ShopifyMutator` methods only. Prompt text in titles or rationale is stored as data; it cannot change risk, tenant, or execute. Duplicate approve and duplicate queue delivery are idempotent.

Phase 10: Terraform-only AWS. RDS is private. There is no ElastiCache. The `edge` task is in a public subnet without NAT ([ADR 0024](adr/0024-cost-optimized-aws-network.md), [ADR 0025](adr/0025-portfolio-cost-envelope.md)); inbound is 80/443 on Caddy only. The worker security group has no inbound rules. Images are non-root and contain no secrets. Secrets Manager JSON is injected by the ECS execution role; the API task role cannot read Secrets Manager or the DLQ. GitHub deploys via OIDC on `main` only. Shopify OAuth URLs are not switched to AWS until HTTPS is verified.

## Prompt injection

Product titles, descriptions, customer notes, order attributes, and the merchant question may contain instructions.

Mitigations:

- System policy and tool authz are code
- Retrieved text labeled as untrusted in prompts
- No tool can change tenant, permissions, or approval state because of text content
- AgentBench includes injection scenarios

## Threats

| Threat | Impact | Mitigation | Test |
|--------|--------|------------|------|
| OAuth CSRF / shop spoofing | Foreign store linked | One-time signed `state`, `*.myshopify.com` allowlist, callback shop match | Forged state, shop swap |
| Offline token theft | Store read/write | Envelope encrypt, isolated table, redaction | No token in API/logs |
| Cross-tenant read | Data leak | TenantContext + FORCE RLS + 404; app role has no BYPASSRLS | Two-merchant fixtures; raw SELECT as `merchantos_app` |
| Prompt injection | Tool abuse | Untrusted data; coded authz | AgentBench suite |
| LLM-built Shopify calls | Arbitrary mutation | No generic HTTP/GraphQL tool | Unknown tool rejected |
| Unauthorized mutation | Price/discount change | PolicyService; MEDIUM/HIGH need merchant ApprovalRecord; CRITICAL blocked; no execute tool | Unapproved `ApprovedAction.load` fails; agent import of mutator fails |
| Webhook forgery / replay | Poisoned data | HMAC, 5-min skew, unique `event_id` | Bad HMAC 401; replay no-op |
| Missing GDPR / uninstall | App review fail; token remains | Mandatory topics; uninstall tombstones token and sessions | Uninstall then ShopifyPort fail-closed |
| Session theft (XSS) | Account takeover | HttpOnly cookie; no tokens in JS | Cookie flag tests |
| Secret in logs | Credential leak | Deny-list logger | Caplog assertions |
| Over-broad IAM | Infra compromise | Separate api/worker task roles | Terraform review |
| Cost bomb | LLM/Shopify spend | Per-merchant rate limits; run budgets | 429 + max_steps |
| Protected customer data | App review failure | Dev store in V1; document prod gate | PII field policy |

## Risk classification (deterministic)

Assigned from `action.type` and affected-row count, not from the model.

| Level | Examples | V1 behavior |
|-------|----------|-------------|
| LOW | Internal insight (not an ActionType) | Persist internally; **never** Shopify write |
| MEDIUM | Product title, description, tags, status (`ACTIVE`/`DRAFT`) | `Action.PROPOSED` + merchant approval |
| HIGH | Single-resource price or discount change | `Action.PROPOSED` + merchant approval |
| CRITICAL | Deletes, bulk price/discount | `Action.BLOCKED` |

`PolicyDecision.verdict` is `require_approval` or `block` only. There is no `allow` that calls Shopify.

## Logging and PII

Structured JSON only. Never log access tokens, HMAC secrets, API keys, passwords, or full customer PII by default. Customer tools omit email until a documented need exists.

## Dependency and container scanning

CI runs lint, typecheck, tests, and security scanning (e.g. pip-audit / npm audit, image scan on build). No laptop deploys to production.
