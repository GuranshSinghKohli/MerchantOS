# MerchantOS Security Model

**Status:** Accepted for V1 planning  
**Related:** [contracts.md](contracts.md), [ADR 0014](adr/0014-tenant-from-job-row.md), [ADR 0013](adr/0013-proposal-vs-approval-types.md), [ADR 0017](adr/0017-oauth-and-mandatory-webhooks.md)

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

## Secrets

| Secret | Store | Consumers |
|--------|-------|-----------|
| Shopify client secret | Secrets Manager / local env | api |
| Offline access tokens | `shopify_credentials` BYTEA, envelope encrypted | shopify adapter |
| Session signing key | Secrets Manager / local env | api |
| LLM API key | Secrets Manager / local env | worker via llm adapter |
| DB credentials | Secrets Manager / compose | api, worker |

Agents never receive raw tokens. `shopify_credentials` is not joined into list queries.

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
| Cross-tenant read | Data leak | TenantContext + RLS + 404 | Two-merchant fixtures |
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
| MEDIUM | Future non-price Shopify-adjacent writes | `Action.PROPOSED` + merchant approval |
| HIGH | Single-resource price or discount change | `Action.PROPOSED` + merchant approval |
| CRITICAL | Deletes, bulk price/discount | `Action.BLOCKED` |

`PolicyDecision.verdict` is `require_approval` or `block` only. There is no `allow` that calls Shopify.

## Logging and PII

Structured JSON only. Never log access tokens, HMAC secrets, API keys, passwords, or full customer PII by default. Customer tools omit email until a documented need exists.

## Dependency and container scanning

CI runs lint, typecheck, tests, and security scanning (e.g. pip-audit / npm audit, image scan on build). No laptop deploys to production.
